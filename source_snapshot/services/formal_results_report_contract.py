"""Canonical Results-boundary report snapshot and artifact manifest.

The adapter consumes a validated, persistence-compatible project result. It
never reads Streamlit state and never retains raw sequence or export payloads
inside the report snapshot or manifest.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from io import StringIO
from typing import Any

from Bio import SeqIO

from services.component_output_provenance import runtime_assisted_component_provenance
from services.formal_report_snapshot import (
    build_formal_report_snapshot,
    validate_formal_report_snapshot,
)


REPORT_CONTRACT_SCHEMA_VERSION = "formal-results-report-contract-v1"
REPORT_MANIFEST_SCHEMA_VERSION = "formal-report-artifact-manifest-v1"
REPORT_ADAPTER_VERSION = "r2-v1"
MAP_RENDERER_CONTRACT_VERSION = "formal-plasmid-map-metadata-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class FormalResultsReportContractError(ValueError):
    """Raised when canonical report facts are absent, stale, or inconsistent."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("ascii"))


def _hash_reference(value: str) -> str:
    return f"sha256:{value}"


def _available(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": "available", "facts": dict(facts)}


def _unavailable(reason: str) -> dict[str, str]:
    return {"status": "unavailable", "reason": reason}


def _require_text(record: Mapping[str, Any], key: str) -> str:
    value = _text(record.get(key))
    if not value:
        raise FormalResultsReportContractError(f"Mandatory persisted field '{key}' is unavailable.")
    return value


def _read_canonical_runtime(
    runtime: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    from services.canonical_construct_runtime import (
        CanonicalConstructRuntimeError,
        active_complete_plasmid_snapshot,
        active_construct_snapshot,
    )

    try:
        cassette = active_construct_snapshot(dict(runtime))
    except CanonicalConstructRuntimeError as exc:
        raise FormalResultsReportContractError(f"Canonical runtime cannot be validated: {exc}") from exc
    active_plasmid_id = _text(runtime.get("active_complete_plasmid_id"))
    active_plasmid = next(
        (
            _mapping(item)
            for item in list(runtime.get("complete_plasmid_constructs") or [])
            if _text(_mapping(item).get("plasmid_id")) == active_plasmid_id
        ),
        {},
    )
    has_complete_evidence = bool(
        _text(active_plasmid.get("generated_nucleotide_sequence"))
        or _text(active_plasmid.get("sequence_checksum"))
        or _text(active_plasmid.get("current_revision"))
        or _text(active_plasmid.get("input_signature"))
    )
    if not has_complete_evidence:
        return cassette, {}
    try:
        return cassette, active_complete_plasmid_snapshot(dict(runtime))
    except CanonicalConstructRuntimeError as exc:
        raise FormalResultsReportContractError(
            f"Authoritative complete-plasmid evidence cannot be validated: {exc}"
        ) from exc


def _runtime_input_signature(runtime: Mapping[str, Any], *, complete: bool) -> str:
    collection = "complete_plasmid_constructs" if complete else "transcription_units"
    active_key = "active_complete_plasmid_id" if complete else "active_transcription_unit_id"
    id_key = "plasmid_id" if complete else "tu_id"
    active_id = _text(runtime.get(active_key))
    row = next(
        (
            _mapping(item)
            for item in list(runtime.get(collection) or [])
            if _text(_mapping(item).get(id_key)) == active_id
        ),
        {},
    )
    return _text(row.get("input_signature"))


def _canonical_state(record: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _mapping(record.get("runtime"))
    if not runtime:
        raise FormalResultsReportContractError("Mandatory persisted canonical runtime is unavailable.")
    record_project_id = _text(record.get("project_id"))
    runtime_project_id = _text(runtime.get("project_id"))
    if record_project_id and runtime_project_id and record_project_id != runtime_project_id:
        raise FormalResultsReportContractError("Persisted project identity does not match canonical runtime identity.")
    cassette, plasmid = _read_canonical_runtime(runtime)

    use_complete = bool(_text(plasmid.get("sequence")))
    canonical = plasmid if use_complete else cassette
    sequence = _text(canonical.get("sequence"))
    checksum = _text(canonical.get("sequence_checksum")).lower()
    status = _text(canonical.get("construct_status"))
    if not sequence or not _SHA256_RE.fullmatch(checksum):
        raise FormalResultsReportContractError("Mandatory canonical sequence identity is unavailable.")
    if _sha256_bytes(sequence.encode("ascii")) != checksum:
        raise FormalResultsReportContractError("Canonical sequence hash does not match canonical bytes.")
    if status != "current":
        raise FormalResultsReportContractError(
            f"Canonical result must be current before report adaptation; received {status or 'unknown'}."
        )
    input_signature = _runtime_input_signature(_mapping(canonical.get("runtime")), complete=use_complete)
    if not _SHA256_RE.fullmatch(input_signature):
        raise FormalResultsReportContractError("Mandatory canonical input signature is unavailable.")
    features = list(canonical.get("feature_rows") or [])
    length = int(canonical.get("sequence_length") or 0)
    for index, raw in enumerate(features):
        feature = _mapping(raw)
        start, end = int(feature.get("start") or 0), int(feature.get("end") or 0)
        if start < 1 or end < start or end > length or int(feature.get("strand") or 0) not in {-1, 1}:
            raise FormalResultsReportContractError(
                f"Canonical feature {index + 1} has invalid coordinates or strand."
            )
    return {
        "runtime": _mapping(canonical.get("runtime")),
        "cassette": cassette,
        "canonical": canonical,
        "sequence": sequence,
        "sequence_sha256": checksum,
        "input_signature": input_signature,
        "contains_vector": use_complete,
        "features": features,
        "topology": _text(canonical.get("topology")) or ("circular" if use_complete else "linear"),
    }


def _component_records(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = _mapping(state.get("runtime"))
    assisted = runtime_assisted_component_provenance(runtime)
    assets = {
        _text(_mapping(item).get("asset_id")): _mapping(item)
        for item in list(runtime.get("sequence_assets") or [])
    }
    components = {
        _text(_mapping(item).get("component_id")): _mapping(item)
        for item in list(runtime.get("components") or [])
    }
    ordered_ids = list(_mapping(state.get("cassette")).get("ordered_component_ids") or [])
    records: list[dict[str, Any]] = []
    for order, component_id in enumerate(ordered_ids, start=1):
        canonical_component_id = _text(component_id)
        component = components.get(canonical_component_id, {})
        asset_id = _text(component.get("sequence_asset_id"))
        asset = assets.get(asset_id, {})
        if (
            not canonical_component_id
            or _text(component.get("component_id")) != canonical_component_id
            or not _text(component.get("display_name"))
            or not _text(component.get("component_type"))
            or not asset_id
            or not asset
        ):
            raise FormalResultsReportContractError(
                f"Canonical component order references incomplete component '{canonical_component_id}'."
            )
        records.append(
            {
                "order": order,
                "component_id": canonical_component_id,
                "name": _text(component.get("display_name")),
                "role": _text(component.get("component_type")),
                "accession": _text(assisted.get(canonical_component_id, {}).get('source_accession') or asset.get("original_record_identifier")),
                "source": _text(assisted.get(canonical_component_id, {}).get('authority') or asset.get("source_type")),
                "length_bp": int(asset.get("length") or 0),
            }
        )
    if not records:
        raise FormalResultsReportContractError("Mandatory persisted component order is unavailable.")
    return records


def _component_authority(state: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _mapping(state.get("runtime"))
    assisted = runtime_assisted_component_provenance(runtime)
    assets = {
        _text(_mapping(item).get("asset_id")): _mapping(item)
        for item in list(runtime.get("sequence_assets") or [])
    }
    components = {
        _text(_mapping(item).get("component_id")): _mapping(item)
        for item in list(runtime.get("components") or [])
    }
    ordered_ids = [_text(item) for item in list(_mapping(state.get("cassette")).get("ordered_component_ids") or [])]
    records: list[dict[str, Any]] = []
    for order, component_id in enumerate(ordered_ids, start=1):
        component = components.get(component_id, {})
        asset_id = _text(component.get("sequence_asset_id"))
        asset = assets.get(asset_id, {})
        checksum = _text(asset.get("sequence_checksum")).lower()
        if not _SHA256_RE.fullmatch(checksum):
            raise FormalResultsReportContractError(
                f"Canonical component '{component_id}' is missing an authoritative asset checksum."
            )
        sequence = asset.get("nucleotide_sequence")
        if isinstance(sequence, str) and sequence:
            normalized_sequence = "".join(sequence.split()).upper()
            if _sha256_bytes(normalized_sequence.encode("ascii")) != checksum:
                raise FormalResultsReportContractError(
                    f"Canonical component '{component_id}' asset checksum contradicts its authoritative sequence."
                )
            if int(asset.get("length") or 0) != len(normalized_sequence):
                raise FormalResultsReportContractError(
                    f"Canonical component '{component_id}' asset length contradicts its authoritative sequence."
                )
        source_file_checksum = _text(asset.get("source_file_checksum")).lower()
        if source_file_checksum and not _SHA256_RE.fullmatch(source_file_checksum):
            raise FormalResultsReportContractError(
                f"Canonical component '{component_id}' has an invalid source-file checksum."
            )
        records.append(
            {
                "order": order,
                "component_id": component_id,
                "component_type": _text(component.get("component_type")),
                "component_provenance": _text(component.get("provenance_reference")),
                "asset_id": asset_id,
                "asset_sha256": _hash_reference(checksum),
                "asset_length_bp": int(asset.get("length") or 0),
                "source_type": _text(asset.get("source_type")),
                "source_name": _text(asset.get("source_name")),
                "source_reference": _text(asset.get("original_record_identifier")),
                "source_file_sha256": _hash_reference(source_file_checksum) if source_file_checksum else "",
                "asset_provenance": _text(asset.get("provenance_reference")),
            }
        )
        if provenance := assisted.get(component_id):
            if (provenance['sequence_sha256'] != checksum
                    or provenance['project_id'] != _text(runtime.get('project_id'))):
                raise FormalResultsReportContractError(
                    f"Assisted provenance for '{component_id}' does not match its canonical asset/project."
                )
            projected = dict(provenance)
            for field in ('sequence_sha256', 'resolution_id'):
                if _SHA256_RE.fullmatch(projected[field]):
                    projected[field] = _hash_reference(projected[field])
            records[-1]['assisted_provenance'] = projected
    return {"records": records, "identity": _hash_reference(_identity(records))}


def _source_facts(record: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    provided_hashes = _mapping(record.get("source_input_sha256"))
    source_inputs = _mapping(record.get("source_inputs"))
    source_hashes = {
        _text(role): _sha256_bytes(value.encode("utf-8"))
        for role, value in sorted(source_inputs.items(), key=lambda item: str(item[0]))
        if _text(role) and isinstance(value, str) and value
    }
    for role, digest in provided_hashes.items():
        if _text(source_hashes.get(_text(role))) != _text(digest).lower():
            raise FormalResultsReportContractError(f"Persisted source hash mismatch for '{role}'.")
    if not source_hashes:
        runtime = _mapping(state.get("runtime"))
        source_hashes = {
            _text(_mapping(asset).get("asset_id")): _text(_mapping(asset).get("sequence_checksum")).lower()
            for asset in list(runtime.get("sequence_assets") or [])
            if _text(_mapping(asset).get("asset_id"))
            and _SHA256_RE.fullmatch(_text(_mapping(asset).get("sequence_checksum")))
        }

    input_records = _mapping(record.get("input_records")) or _mapping(record.get("original_input"))
    record_refs: list[dict[str, Any]] = []
    record_authorities: list[dict[str, Any]] = []
    for role, raw in sorted(input_records.items(), key=lambda item: str(item[0])):
        item = _mapping(raw)
        if not item:
            continue
        asset = _mapping(item.get("asset"))
        record_refs.append(
            {
                "role": _text(role),
                "source_kind": _text(item.get("source_kind") or item.get("source_type")),
                "source_reference": _text(
                    item.get("source_reference")
                    or item.get("accession")
                    or item.get("record_id")
                    or item.get("original_record_identifier")
                    or asset.get("original_record_identifier")
                    or item.get("source_name")
                    or asset.get("source_name")
                ),
                "length_bp": int(
                    item.get("sequence_length")
                    or item.get("length")
                    or asset.get("length")
                    or len(str(item.get("normalized_sequence") or ""))
                ),
            }
        )
        normalized_sequence = item.get("normalized_sequence")
        record_authorities.append(
            {
                "role": _text(role),
                "source_kind": _text(item.get("source_kind") or item.get("source_type")),
                "source_reference": _text(
                    item.get("source_reference")
                    or item.get("accession")
                    or item.get("record_id")
                    or item.get("original_record_identifier")
                    or asset.get("original_record_identifier")
                    or item.get("source_name")
                    or asset.get("source_name")
                ),
                "normalized_asset_sha256": (
                    _hash_reference(_sha256_bytes(normalized_sequence.encode("utf-8")))
                    if isinstance(normalized_sequence, str) and normalized_sequence
                    else ""
                ),
                "recorded_asset_sha256": (
                    _hash_reference(_text(asset.get("sequence_checksum")).lower())
                    if _SHA256_RE.fullmatch(_text(asset.get("sequence_checksum")))
                    else ""
                ),
            }
        )
    return (
        {
            "source_count": len(source_hashes),
            "source_hashes": [
                {"source_id": role, "sha256": _hash_reference(digest)}
                for role, digest in sorted(source_hashes.items())
            ],
        },
        {
            "records": record_refs,
            "identity": _identity(
                {"hashes": source_hashes, "records": record_refs, "authorities": record_authorities}
            ),
        },
    )


def _project_context(record: Mapping[str, Any]) -> dict[str, Any]:
    context = _mapping(record.get("formal_project_context"))
    allowed = (
        "host_key",
        "expression_target",
        "design_scenario",
        "record_kind",
        "formal_editor_state_contract_version",
        "project_context",
        "replacement_strategy_id",
    )
    projected: dict[str, Any] = {}
    for key in allowed:
        value = context.get(key)
        if value is None or value == "":
            continue
        projected[key] = _text(value)
    return projected


def _transcription_unit_records(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = _mapping(state.get("runtime"))
    units = list(runtime.get("expression_units") or [])
    ordered_ids = [_text(item) for item in list(runtime.get("unit_order") or []) if _text(item)]
    by_id = {
        _text(_mapping(unit).get("unit_id") or _mapping(unit).get("tu_id")): _mapping(unit)
        for unit in units
    }
    if ordered_ids:
        units = [by_id[unit_id] for unit_id in ordered_ids if unit_id in by_id]
    records: list[dict[str, Any]] = []
    for order, raw in enumerate(units, start=1):
        unit = _mapping(raw)
        unit_id = _text(unit.get("unit_id") or unit.get("tu_id"))
        ranges = [
            {
                "start": int(_mapping(item).get("start") or 0),
                "end": int(_mapping(item).get("end") or 0),
                "strand": int(_mapping(item).get("strand") or 0),
                "role": _text(_mapping(item).get("role") or _mapping(item).get("component_type")),
            }
            for item in list(unit.get("unit_ranges") or unit.get("ranges") or [])
            if isinstance(item, Mapping)
        ]
        records.append(
            {
                "order": order,
                "unit_id": unit_id,
                "orientation": _text(unit.get("orientation")),
                "length_bp": int(unit.get("length") or unit.get("total_length") or len(_text(unit.get("dna")))),
                "input_signature": (
                    _hash_reference(_text(unit.get("input_signature")))
                    if _SHA256_RE.fullmatch(_text(unit.get("input_signature")))
                    else ""
                ),
                "ranges": ranges,
            }
        )
    return records


def _feature_records(features: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "order": index,
            "feature_id": _text(item.get("feature_id") or item.get("component_id")),
            "name": _text(item.get("name") or item.get("label")),
            "role": _text(item.get("component_type") or item.get("feature_type") or item.get("type")),
            "start": int(item.get("start") or 0),
            "end": int(item.get("end") or 0),
            "strand": int(item.get("strand") or 0),
            "accession": _text(item.get("accession") or item.get("source_accession")),
        }
        for index, item in enumerate((_mapping(row) for row in features), start=1)
    ]


def _validation_facts(state: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    canonical = _mapping(state.get("canonical"))
    summary = _mapping(canonical.get("validation_summary"))
    findings = [
        {
            "rule_id": _text(item.get("rule_id")),
            "rule_version": _text(item.get("rule_version")),
            "severity": _text(item.get("severity")),
            "scope": _text(item.get("scope")),
            "message": _text(item.get("message")),
            "blocking": bool(item.get("blocking")),
        }
        for item in (_mapping(row) for row in list(canonical.get("validation_findings") or []))
    ]
    facts = {
        "run_status": _text(canonical.get("construct_status")),
        "input_signature": _hash_reference(_text(state.get("input_signature"))),
        "blocking_count": int(summary.get("blocking_count") or 0),
        "warning_count": int(summary.get("warning_count") or 0),
        "info_count": int(summary.get("info_count") or 0),
        "findings": findings,
        "rule_versions": sorted({_text(row.get("rule_version")) for row in findings if _text(row.get("rule_version"))}),
    }
    return facts, _identity(facts)


def _artifact_payload(record: Mapping[str, Any], state: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    exports = _mapping(record.get("exports"))
    if artifact_id == "fasta":
        keys = ("fasta",) if bool(state.get("contains_vector")) and "fasta" in exports else (
            "complete_plasmid_fasta" if state.get("contains_vector") else "combined_construct_fasta",
        )
    else:
        keys = ("genbank",) if bool(state.get("contains_vector")) and "genbank" in exports else (
            "complete_plasmid_genbank" if state.get("contains_vector") else "combined_construct_genbank",
        )
    raw = next((_mapping(exports.get(key)) for key in keys if _mapping(exports.get(key))), {})
    data = raw.get("data")
    if not isinstance(data, (str, bytes)) or not data:
        return {}
    payload = data.encode("utf-8") if isinstance(data, str) else data
    supplied_hash = _text(raw.get("sha256") or raw.get("checksum")).lower()
    digest = _sha256_bytes(payload)
    if supplied_hash and supplied_hash != digest:
        raise FormalResultsReportContractError(f"{artifact_id.upper()} artifact hash does not match its bytes.")
    try:
        parsed = next(SeqIO.parse(StringIO(payload.decode("utf-8")), artifact_id))
    except Exception as exc:
        raise FormalResultsReportContractError(f"{artifact_id.upper()} artifact cannot be parsed.") from exc
    if str(parsed.seq).upper() != _text(state.get("sequence")).upper():
        raise FormalResultsReportContractError(
            f"{artifact_id.upper()} artifact sequence does not match the canonical sequence."
        )
    return {
        "artifact_id": artifact_id,
        "status": "available",
        "file_name": _text(raw.get("file_name")),
        "media_type": _text(raw.get("mime")) or "text/plain",
        "size_bytes": len(payload),
        "sha256": digest,
        "canonical_sha256": _text(state.get("sequence_sha256")),
    }


def _map_artifact(record: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(_mapping(record.get("persisted_report_artifacts")).get("plasmid_map"))
    data = raw.get("data")
    if not isinstance(data, (str, bytes)) or not data:
        return {
            "artifact_id": "plasmid_map",
            "status": "unavailable",
            "reason": (
                "no_persisted_deterministic_map_artifact"
                if state.get("contains_vector")
                else "not_applicable_without_complete_plasmid"
            ),
            "renderer_version": MAP_RENDERER_CONTRACT_VERSION,
            "source_feature_sha256": _identity(_feature_records(list(state.get("features") or []))),
        }
    payload = data.encode("utf-8") if isinstance(data, str) else data
    digest = _sha256_bytes(payload)
    if _text(raw.get("sha256")) and _text(raw.get("sha256")).lower() != digest:
        raise FormalResultsReportContractError("Plasmid-map artifact hash does not match its bytes.")
    canonical_hash = _text(raw.get("canonical_sequence_sha256")).lower()
    if canonical_hash != _text(state.get("sequence_sha256")):
        raise FormalResultsReportContractError("Plasmid-map artifact is not bound to the canonical sequence.")
    return {
        "artifact_id": "plasmid_map",
        "status": "available",
        "file_name": _text(raw.get("file_name")),
        "media_type": _text(raw.get("mime")) or "image/png",
        "size_bytes": len(payload),
        "sha256": digest,
        "canonical_sha256": canonical_hash,
        "renderer_version": _require_text(raw, "renderer_version"),
        "source_feature_sha256": _identity(_feature_records(list(state.get("features") or []))),
    }


def _manifest_identity(payload: Mapping[str, Any]) -> str:
    return _identity(payload)


def _workflow_type(record: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    runtime = _mapping(state.get("runtime"))
    runtime_type = _text(runtime.get("project_type"))
    record_type = _text(record.get("project_type"))
    if runtime_type == "multi_tu":
        if record_type and record_type not in {"multi_tu", "dual_tu"}:
            raise FormalResultsReportContractError(
                "Persisted workflow type does not match canonical runtime type."
            )
        return "multi_tu"
    if record_type in {"multi_tu", "dual_tu"}:
        raise FormalResultsReportContractError(
            "Persisted workflow type does not match canonical runtime type."
        )
    return "single_gene"


def validate_report_artifact_manifest(
    manifest: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate manifest identity and its binding to a validated snapshot."""
    data = copy.deepcopy(_mapping(manifest))
    supplied_id = _text(data.pop("manifest_id", None)).lower()
    if not _SHA256_RE.fullmatch(supplied_id):
        raise FormalResultsReportContractError("Manifest ID must be a SHA-256 value.")
    if _manifest_identity(data) != supplied_id:
        raise FormalResultsReportContractError("Manifest ID does not match deterministic contents.")
    validated_snapshot = validate_formal_report_snapshot(snapshot)
    required_fields = {
        "schema_version",
        "adapter_version",
        "project_identity",
        "canonical_sequence_identity",
        "report_snapshot_identity",
        "validation_identity",
        "component_identity",
        "provenance_identity",
        "freshness",
        "artifacts",
    }
    if set(data) != required_fields:
        missing, extra = required_fields - set(data), set(data) - required_fields
        raise FormalResultsReportContractError(
            f"Manifest schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}."
        )
    if data.get("schema_version") != REPORT_MANIFEST_SCHEMA_VERSION:
        raise FormalResultsReportContractError("Unsupported report manifest schema version.")
    if data.get("adapter_version") != REPORT_ADAPTER_VERSION:
        raise FormalResultsReportContractError("Unsupported report adapter version.")
    project_identity = _mapping(data.get("project_identity"))
    snapshot_project = _mapping(validated_snapshot.get("project"))
    if (
        _text(project_identity.get("project_id")) != _text(snapshot_project.get("project_id"))
        or _text(project_identity.get("project_name")) != _text(snapshot_project.get("name"))
        or _text(project_identity.get("workflow_type"))
        != _text(validated_snapshot.get("workflow_type"))
    ):
        raise FormalResultsReportContractError(
            "Manifest project identity does not match ReportSnapshot facts."
        )
    snapshot_identity = _mapping(data.get("report_snapshot_identity"))
    if (
        _text(snapshot_identity.get("schema_version"))
        != _text(validated_snapshot.get("schema_version"))
        or _text(snapshot_identity.get("snapshot_id")) != validated_snapshot["snapshot_id"]
    ):
        raise FormalResultsReportContractError("Manifest ReportSnapshot identity mismatch.")
    canonical = _mapping(data.get("canonical_sequence_identity"))
    if not _SHA256_RE.fullmatch(_text(canonical.get("sha256"))):
        raise FormalResultsReportContractError("Manifest canonical sequence identity is invalid.")
    snapshot_construct = _mapping(validated_snapshot.get("construct_summary"))
    if (
        _text(canonical.get("sha256")) != _text(snapshot_construct.get("canonical_hash"))
        or int(canonical.get("length_bp") or 0)
        != int(snapshot_construct.get("canonical_length_bp") or 0)
        or _text(canonical.get("topology")) != _text(snapshot_construct.get("topology"))
    ):
        raise FormalResultsReportContractError(
            "Manifest canonical sequence identity does not match ReportSnapshot facts."
        )
    validation_identity = _mapping(data.get("validation_identity"))
    snapshot_validation = _mapping(validated_snapshot.get("validation_summary"))
    if _text(validation_identity.get("sha256")) != _text(
        snapshot_validation.get("validation_identity")
    ).removeprefix("sha256:"):
        raise FormalResultsReportContractError(
            "Manifest validation identity does not match ReportSnapshot facts."
        )
    component_identity = _mapping(data.get("component_identity"))
    snapshot_components = _mapping(validated_snapshot.get("component_summary"))
    snapshot_component_authority = _mapping(snapshot_components.get("authority"))
    component_authority_records = list(snapshot_component_authority.get("records") or [])
    if (
        _text(snapshot_component_authority.get("identity")).removeprefix("sha256:")
        != _identity(component_authority_records)
        or
        _text(component_identity.get("sha256"))
        != _text(snapshot_component_authority.get("identity")).removeprefix("sha256:")
        or int(component_identity.get("count") or 0)
        != len(component_authority_records)
        or int(component_identity.get("count") or 0)
        != int(snapshot_components.get("count") or 0)
    ):
        raise FormalResultsReportContractError(
            "Manifest component identity does not match authoritative ReportSnapshot facts."
        )
    provenance_identity = _mapping(data.get("provenance_identity"))
    snapshot_provenance = _mapping(validated_snapshot.get("provenance_summary"))
    if _text(provenance_identity.get("sha256")) != _text(
        snapshot_provenance.get("identity")
    ).removeprefix("sha256:"):
        raise FormalResultsReportContractError(
            "Manifest provenance identity does not match ReportSnapshot facts."
        )
    freshness = _mapping(data.get("freshness"))
    snapshot_freshness = _mapping(validated_snapshot.get("freshness"))
    if (
        _text(freshness.get("state")) != _text(snapshot_freshness.get("state"))
        or _text(freshness.get("input_signature"))
        != _text(snapshot_freshness.get("input_signature")).removeprefix("sha256:")
        or _text(freshness.get("source_state_sha256"))
        != _text(snapshot_freshness.get("source_state_sha256")).removeprefix("sha256:")
    ):
        raise FormalResultsReportContractError(
            "Manifest freshness identity does not match ReportSnapshot facts."
        )
    input_signature = _text(freshness.get("input_signature"))
    if (
        _text(canonical.get("input_signature")) != input_signature
        or _text(validation_identity.get("input_signature")) != input_signature
    ):
        raise FormalResultsReportContractError(
            "Manifest input signatures do not match ReportSnapshot freshness facts."
        )
    snapshot_inputs = _mapping(validated_snapshot.get("biological_inputs"))
    if int(provenance_identity.get("source_count") or 0) != int(
        snapshot_inputs.get("source_count") or 0
    ):
        raise FormalResultsReportContractError(
            "Manifest provenance source count does not match ReportSnapshot facts."
        )
    artifacts = list(data.get("artifacts") or [])
    artifact_ids = [_text(_mapping(item).get("artifact_id")) for item in artifacts]
    if sorted(artifact_ids) != ["fasta", "genbank", "plasmid_map"]:
        raise FormalResultsReportContractError(
            "Manifest artifact inventory must contain FASTA, GenBank, and plasmid-map entries exactly once."
        )
    snapshot_artifacts = list(validated_snapshot.get("delivery_artifacts") or [])
    expected_by_id = {
        _text(_mapping(item).get("artifact_id")): _mapping(item)
        for item in snapshot_artifacts
    }
    if sorted(expected_by_id) != ["fasta", "genbank", "plasmid_map"]:
        raise FormalResultsReportContractError(
            "ReportSnapshot artifact authority is incomplete."
        )
    for artifact in artifacts:
        item = _mapping(artifact)
        artifact_id = _text(item.get("artifact_id"))
        if item != expected_by_id.get(artifact_id):
            raise FormalResultsReportContractError(
                f"Manifest {artifact_id or 'unknown'} artifact claims do not match authoritative ReportSnapshot facts."
            )
        if item.get("status") == "available":
            if not _SHA256_RE.fullmatch(_text(item.get("sha256"))):
                raise FormalResultsReportContractError("Available artifact is missing a valid hash.")
            if _text(item.get("canonical_sha256")) != _text(canonical.get("sha256")):
                raise FormalResultsReportContractError("Artifact canonical sequence binding mismatch.")
        elif item.get("status") != "unavailable" or not _text(item.get("reason")):
            raise FormalResultsReportContractError(
                "Unavailable artifact must carry an explicit reason."
            )
    return {"manifest_id": supplied_id, **data}


def build_formal_results_report_contract(project_record: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic snapshot and manifest from persisted canonical facts."""
    record = _mapping(project_record)
    project_id = _require_text(record, "project_id")
    project_name = _require_text(record, "project_name")
    state = _canonical_state(record)
    context = _project_context(record)
    components = _component_records(state)
    component_authority = _component_authority(state)
    transcription_units = _transcription_unit_records(state)
    source_facts, provenance = _source_facts(record, state)
    features = _feature_records(list(state.get("features") or []))
    validation, validation_id = _validation_facts(state)
    workflow_type = _workflow_type(record, state)
    input_signature = _text(state.get("input_signature"))
    canonical_hash = _text(state.get("sequence_sha256"))

    artifacts = []
    for artifact_id in ("fasta", "genbank"):
        artifact = _artifact_payload(record, state, artifact_id)
        artifacts.append(
            artifact
            or {
                "artifact_id": artifact_id,
                "status": "unavailable",
                "reason": "not_persisted",
            }
        )
    artifacts.append(_map_artifact(record, state))

    host = _available({"host_key": _text(context.get("host_key"))}) if _text(context.get("host_key")) else _unavailable("not_recorded")
    design_goal = (
        _available({"expression_target": _text(context.get("expression_target"))})
        if _text(context.get("expression_target"))
        else _unavailable("not_recorded")
    )
    insertion = _mapping(record.get("insertion_settings")) or _mapping(_mapping(record.get("original_input")).get("insertion_settings"))
    strategy = (
        _available(
            {
                "mode": _text(insertion.get("mode")),
                "start_coordinate": int(insertion.get("start_coordinate") or 0),
                "end_coordinate": int(insertion.get("end_coordinate") or 0),
                "orientation": _text(insertion.get("insertion_orientation")),
                "workflow_id": _text(insertion.get("workflow_id")),
            }
        )
        if insertion
        else _unavailable("not_recorded")
    )
    step_outputs = {
        "step_1": _available({"project_context": context, **source_facts}),
        "step_2": _available({"component_count": len(components), "ordered_component_ids": [row["component_id"] for row in components], "transcription_units": transcription_units}),
        "step_3": _available({"assembly_length_bp": int(_mapping(state.get("cassette")).get("sequence_length") or 0), "assembly_sha256": _hash_reference(_text(_mapping(state.get("cassette")).get("sequence_checksum") or canonical_hash)), "feature_count": len(_mapping(state.get("cassette")).get("feature_rows") or []), "transcription_unit_count": len(transcription_units) or 1}),
        "step_4": strategy,
        "step_5": _available({"validation_identity": _hash_reference(validation_id), **validation}),
        "step_6": _available({"canonical_length_bp": len(_text(state.get("sequence"))), "canonical_sha256": _hash_reference(canonical_hash), "topology": _text(state.get("topology")), "contains_vector": bool(state.get("contains_vector")), "complete_plasmid": (_available({"canonical_length_bp": len(_text(state.get("sequence"))), "canonical_sha256": _hash_reference(canonical_hash), "topology": _text(state.get("topology"))}) if state.get("contains_vector") else _unavailable("not_generated_for_assembly_only_design"))}),
    }
    snapshot = build_formal_report_snapshot(
        workflow_type=workflow_type,
        freshness={"state": "current", "input_signature": _hash_reference(input_signature), "source_state_sha256": _hash_reference(_identity({"project_id": project_id, "context": context, "sources": source_facts, "canonical_sha256": canonical_hash, "features": features, "validation_identity": validation_id}))},
        project={"project_id": project_id, "name": project_name, "project_type": _text(record.get("project_type")) or workflow_type},
        host=host,
        design_goal=design_goal,
        biological_inputs=source_facts,
        component_summary={"components": components, "count": len(components), "authority": component_authority},
        construct_summary={"canonical_construct_present": True, "canonical_length_bp": len(_text(state.get("sequence"))), "canonical_hash": canonical_hash, "cassette_length_bp": int(_mapping(state.get("cassette")).get("sequence_length") or 0), "cassette_sha256": _text(_mapping(state.get("cassette")).get("sequence_checksum")), "topology": _text(state.get("topology")), "complete_plasmid": (_available({"canonical_length_bp": len(_text(state.get("sequence"))), "canonical_sha256": _hash_reference(canonical_hash), "topology": _text(state.get("topology"))}) if state.get("contains_vector") else _unavailable("not_generated_for_assembly_only_design"))},
        feature_summary={"feature_count": len(features), "feature_identity": _hash_reference(_identity(features)), "features": features},
        validation_summary={**validation, "validation_identity": _hash_reference(validation_id)},
        provenance_summary={**provenance, "identity": _hash_reference(provenance["identity"])},
        delivery_artifacts=artifacts,
        route_specific_data={"adapter_version": REPORT_ADAPTER_VERSION, "step_outputs": step_outputs, "crispr": _unavailable("not_applicable_to_formal_expression_vector_report")},
    )

    manifest_payload = {
        "schema_version": REPORT_MANIFEST_SCHEMA_VERSION,
        "adapter_version": REPORT_ADAPTER_VERSION,
        "project_identity": {"project_id": project_id, "project_name": project_name, "workflow_type": workflow_type},
        "canonical_sequence_identity": {"sha256": canonical_hash, "length_bp": len(_text(state.get("sequence"))), "topology": _text(state.get("topology")), "input_signature": input_signature},
        "report_snapshot_identity": {"schema_version": snapshot["schema_version"], "snapshot_id": snapshot["snapshot_id"]},
        "validation_identity": {"sha256": validation_id, "input_signature": input_signature},
        "component_identity": {"sha256": component_authority["identity"].removeprefix("sha256:"), "count": len(components)},
        "provenance_identity": {"sha256": provenance["identity"], "source_count": source_facts["source_count"]},
        "freshness": {"state": "current", "input_signature": input_signature, "source_state_sha256": snapshot["freshness"]["source_state_sha256"].removeprefix("sha256:")},
        "artifacts": artifacts,
    }
    manifest = {"manifest_id": _manifest_identity(manifest_payload), **manifest_payload}
    validated_manifest = validate_report_artifact_manifest(manifest, snapshot)
    return {
        "schema_version": REPORT_CONTRACT_SCHEMA_VERSION,
        "report_snapshot": snapshot,
        "artifact_manifest": validated_manifest,
    }
