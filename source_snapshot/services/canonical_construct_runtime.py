from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from typing import Any
from uuid import uuid4

from core.part_library import PartLibraryManager
from core.pcambia1300_exact_insertion_contract import (
    Pcambia1300ExactInsertionContractError,
    exact_insertion_contract,
    insert_pcambia1300_cassette,
    is_pcambia1300_sequence,
    remap_pcambia1300_features,
    validate_pcambia1300_operation,
)
from services.sequence_service import reverse_complement, seq_hash, translate


R227_RUNTIME_SCHEMA_VERSION = "bds.r227.canonical_single_gene_construct.v1"
R227_RULE_VERSION = "r227.v1"
MULTI_TU_PROJECT_TYPE = "multi_tu"
MULTI_TU_UNIT_ROLE_SPECS = (
    ("promoter", "promoter", True),
    ("five_prime_region", "five_prime_utr", True),
    ("targeting_sequence", "signal_targeting_coding_sequence", False),
    ("cds", "cds", True),
    ("linker", "linker", False),
    ("fusion_tag", "c_terminal_tag", False),
    ("3_prime_regulatory_region", "terminator", True),
)
LEGACY_MULTI_TU_UNIT_ROLE_SPECS = tuple(
    item for item in MULTI_TU_UNIT_ROLE_SPECS if item[0] != "five_prime_region"
)
NUCLEOTIDE_ASSET_ALPHABET = frozenset("ATCGNRYSWKMBDHVU")
CONSTRUCT_READY_DNA_ALPHABET = frozenset("ATCGNRYSWKMBDHV")
PROTEIN_ALPHABET = frozenset("ABCDEFGHIKLMNPQRSTVWXYZ*")

COMPONENT_TYPE_ORDER: tuple[str, ...] = (
    "promoter",
    "five_prime_utr",
    "n_terminal_tag",
    "signal_targeting_coding_sequence",
    "cds",
    "linker",
    "c_terminal_tag",
    "tag",
    "terminator",
)
MANDATORY_COMPONENT_TYPES = {"promoter", "cds", "terminator"}
DISPLAY_COMPONENT_LABELS = {
    "promoter": "Promoter",
    "five_prime_utr": "5' UTR",
    "n_terminal_tag": "N-terminal tag",
    "signal_targeting_coding_sequence": "Signal/targeting coding sequence",
    "cds": "CDS",
    "linker": "Linker",
    "c_terminal_tag": "C-terminal tag",
    "tag": "C-terminal tag",
    "terminator": "Terminator",
}
ALLOWED_TOPOLOGIES = {"", "linear", "circular"}
CANONICAL_COORDINATE_CONVENTION = "1-based-inclusive"
INSERTION_MODES = {"insertion", "replacement"}
ASSET_ROLES = {"generic", "construct_component", "backbone"}


class CanonicalConstructRuntimeError(ValueError):
    """Raised when the canonical construct runtime receives invalid input."""


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _deepcopy(value: Any) -> Any:
    return copy.deepcopy(value)


def _normalize_topology(value: Any) -> str:
    topology = _text(value).lower()
    if topology not in ALLOWED_TOPOLOGIES:
        return ""
    return topology


def _normalize_whitespace_and_case(raw_text: str) -> str:
    return "".join(char for char in str(raw_text or "") if not char.isspace()).upper()


def _checksum_payload(value: Any) -> str:
    return seq_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _finding(
    rule_id: str,
    severity: str,
    affected_object: str,
    explanation: str,
    *,
    blocking: bool,
    affected_coordinate: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "affected_object": affected_object,
        "affected_coordinate": dict(affected_coordinate or {}),
        "explanation": explanation,
        "blocking": blocking,
        "rule_version": R227_RULE_VERSION,
    }


def _contains_invalid_symbols(sequence: str, allowed_alphabet: frozenset[str]) -> list[str]:
    return sorted(set(sequence.upper()) - set(allowed_alphabet))


def _display_interval(start: int, end: int) -> tuple[int, int]:
    return start + 1, end


def _interval_to_zero_based(start: int, end: int) -> tuple[int, int]:
    normalized_start = max(1, int(start or 0))
    normalized_end = max(normalized_start, int(end or normalized_start))
    return normalized_start - 1, normalized_end


def _file_checksum_bytes(value: bytes) -> str:
    if not value:
        return ""
    return hashlib.sha256(value).hexdigest()


def _feature_rows_for_display(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        start = int(feature.get("start", 0))
        end = int(feature.get("end", 0))
        display_start, display_end = _display_interval(start, end)
        row = {
            "name": _text(feature.get("name")),
            "component_type": _text(feature.get("component_type")),
            "start": display_start,
            "end": display_end,
            "strand": int(feature.get("strand", 1) or 1),
            "source_asset_id": _text(feature.get("source_asset_id")),
            "component_id": _text(feature.get("component_id")),
        }
        if _text(feature.get("unit_id")):
            row["unit_id"] = _text(feature.get("unit_id"))
            row["unit_order"] = int(feature.get("unit_order", 0) or 0)
        if _text(feature.get("biological_role")):
            row["biological_role"] = _text(feature.get("biological_role"))
        rows.append(row)
    return rows


def _complete_feature_rows_for_display(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature in features:
        start = int(feature.get("start", 0))
        end = int(feature.get("end", 0))
        display_start, display_end = _display_interval(start, end)
        row = {
            "name": _text(feature.get("name")),
            "feature_type": _text(feature.get("feature_type") or feature.get("type")),
            "source": _text(feature.get("source")),
            "start": display_start,
            "end": display_end,
            "strand": int(feature.get("strand", 1) or 1),
            "component_id": _text(feature.get("component_id")),
            "source_asset_id": _text(feature.get("source_asset_id")),
            "backbone_feature_id": _text(feature.get("backbone_feature_id")),
        }
        location_parts = list(feature.get("location_parts") or [])
        if location_parts:
            row["location_parts"] = [
                {
                    "start": int(part.get("start", 0)) + 1,
                    "end": int(part.get("end", 0)),
                    "strand": int(part.get("strand", feature.get("strand", 1)) or 1),
                }
                for part in location_parts
            ]
            row["location_operator"] = _text(feature.get("location_operator")) or "join"
        if _text(feature.get("unit_id")):
            row["unit_id"] = _text(feature.get("unit_id"))
            row["unit_order"] = int(feature.get("unit_order", 0) or 0)
        if _text(feature.get("biological_role")):
            row["biological_role"] = _text(feature.get("biological_role"))
        rows.append(row)
    return rows


def _revision_id(sequence_checksum: str, input_signature: str) -> str:
    return f"rev-{_checksum_payload({'sequence_checksum': sequence_checksum, 'input_signature': input_signature})[:16]}"


def _normalize_asset_sequence(
    raw_text: str,
    *,
    molecule_type: str,
    source_format: str,
) -> tuple[str, dict[str, Any]]:
    warnings: list[str] = []
    source_metadata: dict[str, Any] = {
        "original_record_id": "",
        "topology": "",
        "imported_feature_records": [],
        "source_record_name": "",
    }
    normalized_format = _text(source_format).lower() or "auto"
    raw_value = str(raw_text or "")

    if molecule_type == "protein":
        sequence = _normalize_whitespace_and_case(raw_value)
        invalid = _contains_invalid_symbols(sequence, PROTEIN_ALPHABET)
        if invalid:
            raise CanonicalConstructRuntimeError(
                f"Protein sequence contains unsupported character(s): {', '.join(invalid)}."
            )
        return sequence, {"warnings": warnings, **source_metadata}

    if normalized_format == "auto":
        normalized_format = "fasta" if raw_value.lstrip().startswith(">") else "plain"

    if normalized_format == "genbank":
        from Bio import SeqIO

        records = list(SeqIO.parse(StringIO(raw_value), "genbank"))
        if not records:
            raise CanonicalConstructRuntimeError("No GenBank record was found in the provided input.")
        if len(records) != 1:
            raise CanonicalConstructRuntimeError("Single-asset intake accepts exactly one GenBank record.")
        record = records[0]
        sequence = _normalize_whitespace_and_case(str(record.seq))
        invalid = _contains_invalid_symbols(sequence, NUCLEOTIDE_ASSET_ALPHABET)
        if invalid:
            raise CanonicalConstructRuntimeError(
                f"GenBank sequence contains unsupported nucleotide symbol(s): {', '.join(invalid)}."
            )
        imported_features: list[dict[str, Any]] = []
        unsupported_feature_detail = False
        for feature in list(record.features or []):
            try:
                raw_qualifiers = feature.qualifiers or {}
                qualifiers = {
                    _text(key): [str(item) for item in values]
                    for key, values in raw_qualifiers.items()
                    if _text(key)
                }
                label = (
                    _text(raw_qualifiers.get("label", [""])[0])
                    or _text(raw_qualifiers.get("gene", [""])[0])
                    or _text(raw_qualifiers.get("note", [""])[0])
                    or _text(feature.type)
                )
                location_parts = list(getattr(feature.location, "parts", None) or [feature.location])
                part_strands = {
                    int(part.strand or feature.location.strand or 1)
                    for part in location_parts
                }
                if len(location_parts) > 1 and len(part_strands) == 1:
                    normalized_parts = [
                        {
                            "start": int(part.start),
                            "end": int(part.end),
                            "strand": int(part.strand or feature.location.strand or 1),
                        }
                        for part in location_parts
                    ]
                    imported_features.append(
                        {
                            "feature_id": _new_id("gbfeature"),
                            "type": _text(feature.type) or "misc_feature",
                            "label": label,
                            "name": label,
                            "strand": int(feature.location.strand or 1),
                            "start": min(int(part["start"]) for part in normalized_parts),
                            "end": max(int(part["end"]) for part in normalized_parts),
                            "location_parts": normalized_parts,
                            "location_operator": _text(getattr(feature.location, "operator", "")) or "join",
                            "qualifiers": qualifiers,
                            "location_text": str(feature.location),
                            "unsupported_location": False,
                        }
                    )
                    continue
                if len(location_parts) > 1:
                    imported_features.append(
                        {
                            "feature_id": _new_id("gbfeature"),
                            "type": _text(feature.type) or "misc_feature",
                            "label": label,
                            "name": label,
                            "strand": int(feature.location.strand or 1),
                            "qualifiers": qualifiers,
                            "location_text": str(feature.location),
                            "unsupported_location": True,
                        }
                    )
                    warnings.append(
                        f"Imported feature '{label}' uses mixed-strand compound location detail that is kept as unsupported metadata only."
                    )
                    continue
                imported_features.append(
                    {
                        "feature_id": _new_id("gbfeature"),
                        "type": _text(feature.type) or "misc_feature",
                        "label": label,
                        "name": label,
                        "start": int(feature.location.start),
                        "end": int(feature.location.end),
                        "strand": int(feature.location.strand or 1),
                        "qualifiers": qualifiers,
                        "location_text": str(feature.location),
                        "unsupported_location": False,
                    }
                )
            except Exception:
                unsupported_feature_detail = True
        if unsupported_feature_detail:
            warnings.append("Unsupported imported feature detail was not fully represented.")
        source_metadata.update(
            {
                "original_record_id": _text(record.id) or _text(record.name),
                "topology": _normalize_topology(record.annotations.get("topology")),
                "imported_feature_records": imported_features,
                "source_record_name": _text(record.name),
            }
        )
        return sequence, {"warnings": warnings, **source_metadata}

    if normalized_format == "fasta":
        try:
            records = PartLibraryManager.parse_fasta(raw_value)
        except ValueError as exc:
            raise CanonicalConstructRuntimeError(str(exc)) from exc
        if len(records) != 1:
            raise CanonicalConstructRuntimeError("Single-asset intake accepts exactly one FASTA record.")
        record = records[0]
        source_metadata.update(
            {
                "original_record_id": _text(record.get("name")),
                "source_record_name": _text(record.get("name")),
            }
        )
        return _text(record.get("sequence")).upper(), {"warnings": warnings, **source_metadata}

    if normalized_format != "plain":
        raise CanonicalConstructRuntimeError(f"Unsupported source format: {normalized_format}")

    sequence = _normalize_whitespace_and_case(raw_value)
    invalid = _contains_invalid_symbols(sequence, NUCLEOTIDE_ASSET_ALPHABET)
    if invalid:
        raise CanonicalConstructRuntimeError(
            f"Sequence contains unsupported nucleotide symbol(s): {', '.join(invalid)}."
        )
    return sequence, {"warnings": warnings, **source_metadata}


def create_sequence_asset(
    *,
    project_id: str,
    display_name: str,
    raw_text: str,
    molecule_type: str = "dna",
    source_type: str = "paste",
    source_format: str = "auto",
    source_name: str = "",
    source_description: str = "",
    provenance_reference: str = "",
    topology: str = "",
    source_file_checksum: str = "",
    asset_role: str = "generic",
    asset_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_type = _text(molecule_type).lower() or "dna"
    if normalized_type not in {"dna", "protein"}:
        raise CanonicalConstructRuntimeError("SequenceAsset molecule_type must be 'dna' or 'protein'.")
    normalized_role = _text(asset_role).lower() or "generic"
    if normalized_role not in ASSET_ROLES:
        raise CanonicalConstructRuntimeError(f"Unsupported SequenceAsset role: {normalized_role}")
    sequence, metadata = _normalize_asset_sequence(
        raw_text,
        molecule_type=normalized_type,
        source_format=source_format,
    )
    created = created_at or _timestamp()
    resolved_topology = _normalize_topology(topology or metadata.get("topology"))
    return {
        "asset_id": asset_id or _new_id("seqasset"),
        "project_id": _text(project_id),
        "display_name": _text(display_name) or _text(metadata.get("source_record_name")) or "Unnamed sequence asset",
        "molecule_type": normalized_type,
        "asset_role": normalized_role,
        "nucleotide_sequence": sequence,
        "length": len(sequence),
        "topology": resolved_topology,
        "source_type": _text(source_type) or "paste",
        "source_name": _text(source_name) or ("pasted-input" if source_type == "paste" else ""),
        "original_record_identifier": _text(metadata.get("original_record_id")),
        "source_description": _text(source_description),
        "sequence_checksum": seq_hash(sequence),
        "source_file_checksum": _text(source_file_checksum),
        "imported_feature_records": _deepcopy(metadata.get("imported_feature_records") or []),
        "provenance_reference": _text(provenance_reference),
        "warnings": [str(item) for item in metadata.get("warnings") or [] if _text(item)],
        "created_at": created,
        "updated_at": _timestamp(),
    }


def create_component(
    *,
    project_id: str,
    component_type: str,
    display_name: str,
    sequence_asset_id: str,
    orientation: str = "forward",
    component_status: str = "draft",
    provenance_reference: str = "",
    user_confirmation_state: str = "user-recorded",
    component_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_type = _text(component_type).lower()
    if normalized_type not in COMPONENT_TYPE_ORDER:
        raise CanonicalConstructRuntimeError(f"Unsupported component type: {normalized_type}")
    normalized_orientation = _text(orientation).lower() or "forward"
    if normalized_orientation not in {"forward", "reverse"}:
        raise CanonicalConstructRuntimeError("Component orientation must be 'forward' or 'reverse'.")
    created = created_at or _timestamp()
    return {
        "component_id": component_id or _new_id("component"),
        "project_id": _text(project_id),
        "component_type": normalized_type,
        "display_name": _text(display_name) or DISPLAY_COMPONENT_LABELS.get(normalized_type, normalized_type),
        "sequence_asset_id": _text(sequence_asset_id),
        "orientation": normalized_orientation,
        "component_status": _text(component_status) or "draft",
        "provenance_reference": _text(provenance_reference),
        "user_confirmation_state": _text(user_confirmation_state) or "user-recorded",
        "created_at": created,
        "updated_at": _timestamp(),
    }


def blank_runtime(project_id: str) -> dict[str, Any]:
    transcription_unit_id = _new_id("tu")
    construct_id = _new_id("construct")
    insertion_site_id = _new_id("insertion")
    plasmid_id = _new_id("plasmid")
    return {
        "schema_version": R227_RUNTIME_SCHEMA_VERSION,
        "project_id": _text(project_id),
        "sequence_assets": [],
        "components": [],
        "transcription_units": [
            {
                "tu_id": transcription_unit_id,
                "project_id": _text(project_id),
                "ordered_component_ids": [],
                "generated_nucleotide_sequence": "",
                "generated_sequence_checksum": "",
                "feature_coordinates": [],
                "validation_findings": [],
                "revision_id": "",
                "generated_at": "",
                "stale": False,
                "input_signature": "",
            }
        ],
        "constructs": [
            {
                "construct_id": construct_id,
                "project_id": _text(project_id),
                "transcription_unit_id": transcription_unit_id,
                "current_revision": "",
                "construct_status": "draft",
                "canonical_generated_sequence": "",
                "validation_summary": {"blocking_count": 0, "warning_count": 0, "info_count": 0},
                "sequence_checksum": "",
                "persistence_identity": construct_id,
                "export_identity": {},
                "input_signature": "",
            }
        ],
        "insertion_sites": [
            {
                "site_id": insertion_site_id,
                "project_id": _text(project_id),
                "backbone_asset_id": "",
                "start_coordinate": 0,
                "end_coordinate": 0,
                "coordinate_convention": CANONICAL_COORDINATE_CONVENTION,
                "mode": "",
                "expected_removed_sequence": "",
                "user_confirmation_state": "",
                "backbone_topology_confirmation_state": "",
                "validation_state": "draft",
                "input_signature": "",
                "created_at": _timestamp(),
                "updated_at": _timestamp(),
            }
        ],
        "complete_plasmid_constructs": [
            {
                "plasmid_id": plasmid_id,
                "project_id": _text(project_id),
                "transcription_unit_id": transcription_unit_id,
                "backbone_asset_id": "",
                "insertion_site_id": insertion_site_id,
                "generated_nucleotide_sequence": "",
                "sequence_checksum": "",
                "topology": "circular",
                "backbone_feature_coordinates": [],
                "inserted_feature_coordinates": [],
                "combined_feature_coordinates": [],
                "validation_findings": [],
                "validation_summary": {"blocking_count": 0, "warning_count": 0, "info_count": 0},
                "cassette_coordinate_span": {},
                "current_revision": "",
                "generated_at": "",
                "construct_status": "draft",
                "persistence_identity": plasmid_id,
                "export_identity": {},
                "input_signature": "",
            }
        ],
        "active_transcription_unit_id": transcription_unit_id,
        "active_construct_id": construct_id,
        "active_insertion_site_id": insertion_site_id,
        "active_complete_plasmid_id": plasmid_id,
    }


def ensure_runtime(project_id: str, runtime_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(runtime_payload, dict) or not runtime_payload:
        return blank_runtime(project_id)
    runtime = _deepcopy(runtime_payload)
    runtime.setdefault("schema_version", R227_RUNTIME_SCHEMA_VERSION)
    runtime["project_id"] = _text(runtime.get("project_id")) or _text(project_id)
    runtime["sequence_assets"] = list(runtime.get("sequence_assets") or [])
    runtime["components"] = list(runtime.get("components") or [])
    runtime["transcription_units"] = list(runtime.get("transcription_units") or [])
    runtime["constructs"] = list(runtime.get("constructs") or [])
    runtime["insertion_sites"] = list(runtime.get("insertion_sites") or [])
    runtime["complete_plasmid_constructs"] = list(runtime.get("complete_plasmid_constructs") or [])
    if not runtime["transcription_units"] or not runtime["constructs"]:
        blank = blank_runtime(project_id)
        runtime.setdefault("sequence_assets", [])
        runtime.setdefault("components", [])
        runtime["transcription_units"] = runtime["transcription_units"] or blank["transcription_units"]
        runtime["constructs"] = runtime["constructs"] or blank["constructs"]
        runtime["active_transcription_unit_id"] = runtime.get("active_transcription_unit_id") or blank["active_transcription_unit_id"]
        runtime["active_construct_id"] = runtime.get("active_construct_id") or blank["active_construct_id"]
    if not runtime["insertion_sites"] or not runtime["complete_plasmid_constructs"]:
        blank = blank_runtime(project_id)
        runtime["insertion_sites"] = runtime["insertion_sites"] or blank["insertion_sites"]
        runtime["complete_plasmid_constructs"] = runtime["complete_plasmid_constructs"] or blank["complete_plasmid_constructs"]
        runtime["active_insertion_site_id"] = runtime.get("active_insertion_site_id") or blank["active_insertion_site_id"]
        runtime["active_complete_plasmid_id"] = runtime.get("active_complete_plasmid_id") or blank["active_complete_plasmid_id"]
    runtime["active_transcription_unit_id"] = _text(runtime.get("active_transcription_unit_id")) or _text(runtime["transcription_units"][0].get("tu_id"))
    runtime["active_construct_id"] = _text(runtime.get("active_construct_id")) or _text(runtime["constructs"][0].get("construct_id"))
    runtime["active_insertion_site_id"] = _text(runtime.get("active_insertion_site_id")) or _text(runtime["insertion_sites"][0].get("site_id"))
    runtime["active_complete_plasmid_id"] = _text(runtime.get("active_complete_plasmid_id")) or _text(runtime["complete_plasmid_constructs"][0].get("plasmid_id"))
    return runtime


def _index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = _text(item.get(key))
        if item_id:
            index[item_id] = item
    return index


def _active_transcription_unit(runtime: dict[str, Any]) -> dict[str, Any]:
    active_id = _text(runtime.get("active_transcription_unit_id"))
    return _index_by(list(runtime.get("transcription_units") or []), "tu_id").get(active_id, {})


def _active_construct(runtime: dict[str, Any]) -> dict[str, Any]:
    active_id = _text(runtime.get("active_construct_id"))
    return _index_by(list(runtime.get("constructs") or []), "construct_id").get(active_id, {})


def _active_insertion_site(runtime: dict[str, Any]) -> dict[str, Any]:
    active_id = _text(runtime.get("active_insertion_site_id"))
    return _index_by(list(runtime.get("insertion_sites") or []), "site_id").get(active_id, {})


def _active_complete_plasmid(runtime: dict[str, Any]) -> dict[str, Any]:
    active_id = _text(runtime.get("active_complete_plasmid_id"))
    return _index_by(list(runtime.get("complete_plasmid_constructs") or []), "plasmid_id").get(active_id, {})


def _mark_complete_plasmid_stale(runtime: dict[str, Any]) -> dict[str, Any]:
    complete_plasmid = _active_complete_plasmid(runtime)
    if complete_plasmid:
        complete_plasmid["construct_status"] = "stale"
    return runtime


def _mark_active_outputs_stale(runtime: dict[str, Any]) -> dict[str, Any]:
    transcription_unit = _active_transcription_unit(runtime)
    construct = _active_construct(runtime)
    if transcription_unit:
        transcription_unit["stale"] = True
    if construct:
        construct["construct_status"] = "stale"
    return _mark_complete_plasmid_stale(runtime)


def upsert_sequence_asset(runtime_payload: dict[str, Any] | None, asset: dict[str, Any]) -> dict[str, Any]:
    runtime = ensure_runtime(_text(asset.get("project_id")), runtime_payload)
    asset_id = _text(asset.get("asset_id"))
    if not asset_id:
        raise CanonicalConstructRuntimeError("SequenceAsset is missing asset_id.")
    updated_assets: list[dict[str, Any]] = []
    replaced = False
    for existing in list(runtime.get("sequence_assets") or []):
        if _text(existing.get("asset_id")) == asset_id:
            updated_assets.append(_deepcopy(asset))
            replaced = True
        else:
            updated_assets.append(existing)
    if not replaced:
        updated_assets.append(_deepcopy(asset))
    runtime["sequence_assets"] = updated_assets
    component_asset_ids = {
        _text(component.get("sequence_asset_id"))
        for component in list(runtime.get("components") or [])
        if _text(component.get("sequence_asset_id"))
    }
    if _text(asset.get("asset_role")) == "backbone" and asset_id not in component_asset_ids:
        return _mark_complete_plasmid_stale(runtime)
    return _mark_active_outputs_stale(runtime)


def upsert_component(runtime_payload: dict[str, Any] | None, component: dict[str, Any]) -> dict[str, Any]:
    runtime = ensure_runtime(_text(component.get("project_id")), runtime_payload)
    component_id = _text(component.get("component_id"))
    if not component_id:
        raise CanonicalConstructRuntimeError("Component is missing component_id.")
    updated_components: list[dict[str, Any]] = []
    replaced = False
    for existing in list(runtime.get("components") or []):
        if _text(existing.get("component_id")) == component_id:
            updated_components.append(_deepcopy(component))
            replaced = True
        else:
            updated_components.append(existing)
    if not replaced:
        updated_components.append(_deepcopy(component))
    runtime["components"] = updated_components
    return _mark_active_outputs_stale(runtime)


def set_active_component_order(runtime_payload: dict[str, Any] | None, ordered_component_ids: list[str]) -> dict[str, Any]:
    runtime = ensure_runtime(_text((runtime_payload or {}).get("project_id")), runtime_payload)
    transcription_unit = _active_transcription_unit(runtime)
    if not transcription_unit:
        raise CanonicalConstructRuntimeError("Active TranscriptionUnit is not available.")
    transcription_unit["ordered_component_ids"] = [_text(item) for item in ordered_component_ids if _text(item)]
    return _mark_active_outputs_stale(runtime)


def create_insertion_site(
    *,
    project_id: str,
    backbone_asset_id: str,
    start_coordinate: int,
    end_coordinate: int,
    mode: str,
    coordinate_convention: str = CANONICAL_COORDINATE_CONVENTION,
    expected_removed_sequence: str = "",
    insertion_orientation: str = "forward",
    user_confirmation: bool = False,
    topology_confirmation: bool = False,
    site_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    normalized_mode = _text(mode).lower()
    if normalized_mode not in INSERTION_MODES:
        raise CanonicalConstructRuntimeError(f"Unsupported insertion mode: {normalized_mode}")
    normalized_orientation = _text(insertion_orientation).lower() or "forward"
    if normalized_orientation not in {"forward", "reverse"}:
        raise CanonicalConstructRuntimeError("Insertion orientation must be 'forward' or 'reverse'.")
    return {
        "site_id": site_id or _new_id("insertion"),
        "project_id": _text(project_id),
        "backbone_asset_id": _text(backbone_asset_id),
        "start_coordinate": int(start_coordinate or 0),
        "end_coordinate": int(end_coordinate or 0),
        "coordinate_convention": _text(coordinate_convention) or CANONICAL_COORDINATE_CONVENTION,
        "mode": normalized_mode,
        "expected_removed_sequence": _normalize_whitespace_and_case(expected_removed_sequence),
        "insertion_orientation": normalized_orientation,
        "user_confirmation_state": "confirmed" if user_confirmation else "",
        "backbone_topology_confirmation_state": "assume-circular" if topology_confirmation else "",
        "validation_state": "draft",
        "input_signature": "",
        "created_at": created_at or _timestamp(),
        "updated_at": _timestamp(),
    }


def upsert_insertion_site(runtime_payload: dict[str, Any] | None, insertion_site: dict[str, Any]) -> dict[str, Any]:
    runtime = ensure_runtime(_text(insertion_site.get("project_id")), runtime_payload)
    site_id = _text(insertion_site.get("site_id"))
    if not site_id:
        raise CanonicalConstructRuntimeError("InsertionSite is missing site_id.")
    updated_sites: list[dict[str, Any]] = []
    replaced = False
    for existing in list(runtime.get("insertion_sites") or []):
        if _text(existing.get("site_id")) == site_id:
            updated_sites.append(_deepcopy(insertion_site))
            replaced = True
        else:
            updated_sites.append(existing)
    if not replaced:
        updated_sites.append(_deepcopy(insertion_site))
    runtime["insertion_sites"] = updated_sites
    runtime["active_insertion_site_id"] = site_id
    complete_plasmid = _active_complete_plasmid(runtime)
    if complete_plasmid:
        complete_plasmid["backbone_asset_id"] = _text(insertion_site.get("backbone_asset_id"))
        complete_plasmid["insertion_site_id"] = site_id
    return _mark_complete_plasmid_stale(runtime)


def _duplicate_id_findings(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    collections = (
        ("sequence asset", "sequence_assets", "asset_id"),
        ("component", "components", "component_id"),
        ("transcription unit", "transcription_units", "tu_id"),
        ("construct", "constructs", "construct_id"),
        ("insertion site", "insertion_sites", "site_id"),
        ("complete plasmid construct", "complete_plasmid_constructs", "plasmid_id"),
    )
    for label, collection_name, key in collections:
        seen: set[str] = set()
        duplicated: set[str] = set()
        for item in list(runtime.get(collection_name) or []):
            item_id = _text(item.get(key))
            if item_id in seen:
                duplicated.add(item_id)
            if item_id:
                seen.add(item_id)
        if duplicated:
            findings.append(
                _finding(
                    "duplicate_authoritative_construct_identity",
                    "error",
                    label,
                    f"Duplicate {label} id(s) detected: {', '.join(sorted(duplicated))}.",
                    blocking=True,
                )
            )
    return findings


def _build_component_snapshot(component: dict[str, Any], asset: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "component_id": _text(component.get("component_id")),
        "component_type": _text(component.get("component_type")),
        "orientation": _text(component.get("orientation")),
        "sequence_asset_id": _text(component.get("sequence_asset_id")),
        "asset_checksum": _text((asset or {}).get("sequence_checksum")),
        "asset_sequence": _text((asset or {}).get("nucleotide_sequence")),
        "asset_type": _text((asset or {}).get("molecule_type")),
    }


def _multi_tu_component_id(unit: dict[str, Any], role: str) -> str:
    aliases = {
        "3_prime_regulatory_region": ("3_prime_regulatory_region", "terminator"),
        "targeting_sequence": ("targeting_sequence", "targeting"),
        "fusion_tag": ("fusion_tag", "c_terminal_tag", "tag"),
    }
    for key in aliases.get(role, (role,)):
        value = unit.get(key)
        component_id = _text(value.get("component_id")) if isinstance(value, dict) else _text(value)
        if component_id:
            return component_id
    return ""


def _multi_tu_role_specs(unit: dict[str, Any]) -> tuple[tuple[str, str, bool], ...]:
    """Keep persisted three-role units readable without mutating their identity."""
    if not _multi_tu_component_id(unit, "five_prime_region"):
        return LEGACY_MULTI_TU_UNIT_ROLE_SPECS
    return MULTI_TU_UNIT_ROLE_SPECS


def _multi_tu_assembly_context(
    runtime: dict[str, Any],
    ordered_ids: list[str],
    component_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if _text(runtime.get("project_type")) != MULTI_TU_PROJECT_TYPE:
        return {
            "enabled": False,
            "findings": [],
            "component_context": {},
            "ordered_units": [],
            "expected_component_ids": [],
        }

    findings: list[dict[str, Any]] = []
    units = [dict(item) for item in list(runtime.get("expression_units") or []) if isinstance(item, dict)]
    if not units:
        findings.append(
            _finding(
                "multi_tu_requires_at_least_one_unit",
                "error",
                "MultiTUConstruct",
                "A multi-TU construct must contain at least one expression unit.",
                blocking=True,
            )
        )

    unit_ids = [_text(unit.get("unit_id")) for unit in units]
    if any(not unit_id for unit_id in unit_ids) or len(set(unit_ids)) != len(unit_ids):
        findings.append(
            _finding(
                "duplicate_or_missing_multi_tu_unit_id",
                "error",
                "MultiTUConstruct",
                "Each expression unit must have a distinct non-empty unit_id.",
                blocking=True,
            )
        )

    orders = [int(unit.get("order", 0) or 0) for unit in units]
    expected_orders = list(range(1, len(units) + 1))
    if sorted(orders) != expected_orders or len(set(orders)) != len(orders):
        findings.append(
            _finding(
                "invalid_multi_tu_order",
                "error",
                "MultiTUConstruct",
                "Expression-unit order must contain every position from 1 through the unit count exactly once.",
                blocking=True,
            )
        )

    ordered_units = sorted(units, key=lambda item: (int(item.get("order", 0) or 0), _text(item.get("unit_id"))))
    component_context: dict[str, dict[str, Any]] = {}
    expected_component_ids: list[str] = []
    seen_component_ids: set[str] = set()
    for unit in ordered_units:
        unit_id = _text(unit.get("unit_id"))
        orientation = _text(unit.get("orientation")).lower()
        if orientation not in {"forward", "reverse"}:
            findings.append(
                _finding(
                    "invalid_multi_tu_orientation",
                    "error",
                    f"ExpressionUnit:{unit_id or 'missing'}",
                    "Expression-unit orientation must be forward or reverse.",
                    blocking=True,
                )
            )
        role_specs = _multi_tu_role_specs(unit)
        if orientation == "reverse":
            role_specs = tuple(reversed(role_specs))
        for role, component_type, required in role_specs:
            component_id = _multi_tu_component_id(unit, role)
            component = component_index.get(component_id)
            if not component_id or component is None:
                if not required:
                    continue
                findings.append(
                    _finding(
                        "missing_multi_tu_component_reference",
                        "error",
                        f"ExpressionUnit:{unit_id or 'missing'}",
                        f"Expression unit '{unit_id or 'missing'}' is missing its {role} component reference.",
                        blocking=True,
                    )
                )
                continue
            if _text(component.get("component_type")) != component_type:
                findings.append(
                    _finding(
                        "invalid_multi_tu_component_role",
                        "error",
                        f"Component:{component_id}",
                        f"Component '{component_id}' is not recorded as the required {role} role.",
                        blocking=True,
                    )
                )
            if component_id in seen_component_ids:
                findings.append(
                    _finding(
                        "duplicate_multi_tu_component_use",
                        "error",
                        f"Component:{component_id}",
                        "A component may occur only once across the expression units.",
                        blocking=True,
                    )
                )
            seen_component_ids.add(component_id)
            expected_component_ids.append(component_id)
            component_context[component_id] = {
                "unit_id": unit_id,
                "unit_name": _text(unit.get("unit_name")) or unit_id,
                "unit_orientation": orientation,
                "unit_order": int(unit.get("order", 0) or 0),
                "role": role,
                "biological_role": role,
            }

    if ordered_ids != expected_component_ids:
        findings.append(
            _finding(
                "multi_tu_component_order_mismatch",
                "error",
                "MultiTUConstruct",
                "The canonical component order does not match the expression-unit definitions.",
                blocking=True,
            )
        )

    return {
        "enabled": True,
        "findings": findings,
        "component_context": component_context,
        "ordered_units": ordered_units,
        "expected_component_ids": expected_component_ids,
    }


def _feature_label(feature: dict[str, Any]) -> str:
    qualifiers = feature.get("qualifiers") if isinstance(feature.get("qualifiers"), dict) else {}
    return (
        _text(feature.get("name"))
        or _text(feature.get("label"))
        or _text((qualifiers.get("label") or [""])[0] if qualifiers else "")
        or _text((qualifiers.get("gene") or [""])[0] if qualifiers else "")
        or _text(feature.get("type"))
        or "Feature"
    )


def _export_feature(feature: dict[str, Any]) -> dict[str, Any]:
    start = int(feature.get("start", 0))
    end = int(feature.get("end", 0))
    display_start, display_end = _display_interval(start, end)
    payload = {
        "name": _feature_label(feature),
        "label": _feature_label(feature),
        "type": _text(feature.get("feature_type") or feature.get("type")) or "misc_feature",
        "start": display_start,
        "end": display_end,
        "strand": int(feature.get("strand", 1) or 1),
    }
    qualifiers = feature.get("qualifiers") if isinstance(feature.get("qualifiers"), dict) else {}
    if qualifiers:
        payload["qualifiers"] = {
            _text(key): [str(item) for item in values]
            for key, values in qualifiers.items()
            if _text(key)
        }
    for key in ("component_id", "source_asset_id", "backbone_feature_id", "source"):
        if _text(feature.get(key)):
            payload[key] = _text(feature.get(key))
    location_parts = list(feature.get("location_parts") or [])
    if location_parts:
        payload["location_parts"] = [
            {
                "start": int(part.get("start", 0)) + 1,
                "end": int(part.get("end", 0)),
                "strand": int(part.get("strand", feature.get("strand", 1)) or 1),
            }
            for part in location_parts
        ]
        payload["location_operator"] = _text(feature.get("location_operator")) or "join"
    return payload


def _stable_complete_plasmid_export_features(
    features: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert runtime-linked features into stable, reviewable export annotations."""
    asset_checksums = {
        _text(asset.get("asset_id")): _text(asset.get("sequence_checksum"))
        for asset in assets
        if _text(asset.get("asset_id"))
    }
    export_features: list[dict[str, Any]] = []
    transient_qualifiers = {"component_id", "source_asset_id", "backbone_feature_id", "traceability", "unit_id"}
    unit_semantics: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        runtime_unit_id = _text(feature.get("unit_id"))
        if not runtime_unit_id:
            continue
        unit_semantics.setdefault(runtime_unit_id, []).append(
            {
                "unit_order": int(feature.get("unit_order", 0) or 0),
                "unit_name": _text(feature.get("unit_name")),
                "name": _feature_label(feature),
                "feature_type": _text(feature.get("feature_type") or feature.get("type")) or "misc_feature",
                "component_type": _text(feature.get("component_type")),
                "biological_role": _text(feature.get("biological_role")),
                "start": int(feature.get("start", 0)),
                "end": int(feature.get("end", 0)),
                "strand": int(feature.get("strand", 1) or 1),
                "sequence_checksum": asset_checksums.get(_text(feature.get("source_asset_id")), ""),
            }
        )
    stable_unit_ids = {}
    for runtime_unit_id, semantics in unit_semantics.items():
        uuid_suffix = runtime_unit_id.removeprefix("tu-")
        is_runtime_uuid = (
            runtime_unit_id.startswith("tu-")
            and len(uuid_suffix) == 32
            and all(character in "0123456789abcdefABCDEF" for character in uuid_suffix)
        )
        stable_unit_ids[runtime_unit_id] = (
            f"tu-{min(item['unit_order'] for item in semantics):03d}-"
            f"{_checksum_payload(sorted(semantics, key=lambda item: _checksum_payload(item)))[:16]}"
            if is_runtime_uuid
            else runtime_unit_id
        )

    for feature in features:
        name = _feature_label(feature)
        raw_qualifiers = feature.get("qualifiers") if isinstance(feature.get("qualifiers"), dict) else {}
        qualifiers = {
            _text(key): sorted(str(item) for item in values)
            for key, values in raw_qualifiers.items()
            if _text(key) and _text(key) not in transient_qualifiers
        }
        qualifiers["label"] = [name]
        runtime_unit_id = _text(feature.get("unit_id"))
        if runtime_unit_id:
            qualifiers["unit_id"] = [stable_unit_ids[runtime_unit_id]]
        source = _text(feature.get("source"))
        start, end = _display_interval(int(feature.get("start", 0)), int(feature.get("end", 0)))
        feature_type = _text(feature.get("feature_type") or feature.get("type")) or "misc_feature"
        if _text(feature.get("unit_id")) and len(feature_type) > 15:
            feature_type = "misc_feature"
        payload = {
            "name": name,
            "label": name,
            "type": feature_type,
            "start": start,
            "end": end,
            "strand": int(feature.get("strand", 1) or 1),
            "qualifiers": {key: qualifiers[key] for key in sorted(qualifiers)},
            "source": source,
        }
        location_parts = list(feature.get("location_parts") or [])
        if location_parts:
            payload["location_parts"] = [
                {
                    "start": int(part.get("start", 0)) + 1,
                    "end": int(part.get("end", 0)),
                    "strand": int(part.get("strand", feature.get("strand", 1)) or 1),
                }
                for part in location_parts
            ]
            payload["location_operator"] = _text(feature.get("location_operator")) or "join"
        if source == "transcription_unit":
            component_type = _text(feature.get("component_type") or feature.get("feature_type")) or "component"
            checksum = asset_checksums.get(_text(feature.get("source_asset_id")), "")
            stable_suffix = checksum[:16] or _checksum_payload(
                {"component_type": component_type, "name": name, "start": start, "end": end}
            )[:16]
            payload["component_id"] = f"component-{component_type}-{stable_suffix}"
            payload["source_asset_id"] = f"seqasset-{stable_suffix}"
            payload["traceability"] = (
                f"Derived from R227 {component_type} component {name} and sequence SHA-256 {checksum or stable_suffix}."
            )
        elif source == "backbone":
            stable_suffix = _checksum_payload(
                {
                    "type": payload["type"],
                    "name": name,
                    "start": start,
                    "end": end,
                    "strand": payload["strand"],
                    "qualifiers": payload["qualifiers"],
                }
            )[:16]
            payload["backbone_feature_id"] = f"backbone-feature-{stable_suffix}"
        export_features.append(payload)

    return sorted(
        export_features,
        key=lambda item: (
            int(item["start"]),
            int(item["end"]),
            _text(item["type"]),
            _text(item["name"]),
            int(item["strand"]),
            _checksum_payload(item.get("qualifiers") or {}),
        ),
    )


def _asset_feature_signature(asset: dict[str, Any]) -> str:
    relevant = {
        "asset_id": _text(asset.get("asset_id")),
        "sequence_checksum": _text(asset.get("sequence_checksum")),
        "topology": _text(asset.get("topology")),
        "imported_feature_records": list(asset.get("imported_feature_records") or []),
    }
    return _checksum_payload(relevant)


def _feature_overlaps_interval(feature: dict[str, Any], start0: int, end0: int) -> bool:
    parts = list(feature.get("location_parts") or [])
    if not parts:
        parts = [{"start": feature.get("start", 0), "end": feature.get("end", 0)}]
    return any(
        int(part.get("start", 0)) < end0 and int(part.get("end", 0)) > start0
        for part in parts
    )


def _feature_crosses_insertion_boundary(feature: dict[str, Any], cut_index: int) -> bool:
    parts = list(feature.get("location_parts") or [])
    if not parts:
        parts = [{"start": feature.get("start", 0), "end": feature.get("end", 0)}]
    return any(
        int(part.get("start", 0)) < cut_index < int(part.get("end", 0))
        for part in parts
    )


def _is_record_source_feature(feature: dict[str, Any]) -> bool:
    """Return True for the record-wide GenBank source container annotation."""
    return _text(feature.get("type")).lower() == "source"


def _shift_feature_after_boundary(
    feature: dict[str, Any], *, boundary: int, delta: int
) -> dict[str, Any]:
    shifted = _deepcopy(feature)
    if _is_record_source_feature(feature):
        # A GenBank source feature describes the whole record. It is preserved
        # and expanded with the composed plasmid instead of treated as a
        # biological feature crossing every possible insertion boundary.
        shifted["end"] = int(feature.get("end", 0)) + delta
        shifted["location_parts"] = []
        return shifted
    location_parts = list(feature.get("location_parts") or [])
    if location_parts:
        shifted_parts: list[dict[str, int]] = []
        for part in location_parts:
            start = int(part.get("start", 0))
            end = int(part.get("end", 0))
            if start >= boundary:
                start += delta
                end += delta
            shifted_parts.append(
                {
                    "start": start,
                    "end": end,
                    "strand": int(part.get("strand", feature.get("strand", 1)) or 1),
                }
            )
        shifted["location_parts"] = shifted_parts
        shifted["start"] = min(part["start"] for part in shifted_parts)
        shifted["end"] = max(part["end"] for part in shifted_parts)
    elif int(feature.get("start", 0)) >= boundary:
        shifted["start"] = int(feature.get("start", 0)) + delta
        shifted["end"] = int(feature.get("end", 0)) + delta
    return shifted


def _validate_insertion_site_against_backbone(
    insertion_site: dict[str, Any],
    backbone_asset: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    backbone_length = len(_text(backbone_asset.get("nucleotide_sequence")))
    mode = _text(insertion_site.get("mode")).lower()
    start_coordinate = int(insertion_site.get("start_coordinate", 0) or 0)
    end_coordinate = int(insertion_site.get("end_coordinate", 0) or 0)
    cut_index = -1
    replacement_start0 = -1
    replacement_end0 = -1
    removed_sequence = ""
    exact_contract: dict[str, Any] = {}

    if not _text(backbone_asset.get("asset_id")):
        findings.append(
            _finding(
                "missing_backbone",
                "error",
                "InsertionSite",
                "A backbone SequenceAsset is required before complete plasmid generation.",
                blocking=True,
            )
        )
        return findings, {}
    if _text(backbone_asset.get("molecule_type")).lower() == "protein":
        findings.append(
            _finding(
                "protein_only_backbone",
                "error",
                f"SequenceAsset:{backbone_asset.get('asset_id')}",
                f"Protein-only asset '{backbone_asset.get('display_name')}' cannot be used as a nucleotide backbone.",
                blocking=True,
            )
        )
    if not _text(backbone_asset.get("nucleotide_sequence")):
        findings.append(
            _finding(
                "backbone_has_no_nucleotide_sequence",
                "error",
                f"SequenceAsset:{backbone_asset.get('asset_id')}",
                "Backbone asset has no nucleotide sequence.",
                blocking=True,
            )
        )
    if mode not in INSERTION_MODES:
        findings.append(
            _finding(
                "ambiguous_insertion_mode",
                "error",
                "InsertionSite",
                "Insertion mode must be either insertion or replacement.",
                blocking=True,
            )
        )
    if _text(insertion_site.get("user_confirmation_state")) != "confirmed":
        findings.append(
            _finding(
                "missing_insertion_site_confirmation",
                "error",
                "InsertionSite",
                "Insertion or replacement coordinates must be explicitly confirmed before complete plasmid generation.",
                blocking=True,
            )
        )

    topology = _normalize_topology(backbone_asset.get("topology"))
    if topology == "":
        if _text(insertion_site.get("backbone_topology_confirmation_state")) == "assume-circular":
            findings.append(
                _finding(
                    "backbone_topology_confirmed_by_user",
                    "warning",
                    f"SequenceAsset:{backbone_asset.get('asset_id')}",
                    "Backbone topology was absent in the imported record and was confirmed as circular by the user.",
                    blocking=False,
                )
            )
            topology = "circular"
        else:
            findings.append(
                _finding(
                    "backbone_topology_requires_confirmation",
                    "error",
                    f"SequenceAsset:{backbone_asset.get('asset_id')}",
                    "Backbone topology is absent and must be confirmed as circular before complete plasmid generation.",
                    blocking=True,
                )
            )

    backbone_sequence = _text(backbone_asset.get("nucleotide_sequence"))
    contract_snapshot = insertion_site.get("exact_insertion_contract")
    if is_pcambia1300_sequence(backbone_sequence) or isinstance(contract_snapshot, dict):
        try:
            exact_contract = validate_pcambia1300_operation(
                source_sequence=backbone_sequence,
                accession_version=_text(backbone_asset.get("original_record_identifier")),
                circular=topology == "circular",
                mode=mode,
                start_coordinate=start_coordinate,
                end_coordinate=end_coordinate,
                insertion_orientation=_text(insertion_site.get("insertion_orientation")) or "forward",
                workflow_id=_text(insertion_site.get("workflow_id")),
            )
            if contract_snapshot != exact_contract:
                raise Pcambia1300ExactInsertionContractError(
                    "The saved AF234296.1 exact-insertion contract does not match the immutable contract version."
                )
        except Pcambia1300ExactInsertionContractError as exc:
            findings.append(
                _finding(
                    "pcambia1300_exact_insertion_contract_mismatch",
                    "error",
                    "InsertionSite",
                    str(exc),
                    blocking=True,
                )
            )

    if mode == "insertion":
        valid_neighbors = (
            1 <= start_coordinate <= backbone_length
            and (
                end_coordinate == start_coordinate + 1
                or (
                    topology == "circular"
                    and start_coordinate == backbone_length
                    and end_coordinate == 1
                )
            )
        )
        if not valid_neighbors:
            findings.append(
                _finding(
                    "invalid_insertion_coordinate",
                    "error",
                    "InsertionSite",
                    "Insertion mode requires two adjacent 1-based backbone coordinates, including the circular boundary case length->1.",
                    blocking=True,
                )
            )
        cut_index = start_coordinate
    elif mode == "replacement":
        if start_coordinate < 1 or end_coordinate < 1 or start_coordinate > backbone_length or end_coordinate > backbone_length:
            findings.append(
                _finding(
                    "insertion_interval_outside_backbone_bounds",
                    "error",
                    "InsertionSite",
                    "Replacement coordinates fall outside the backbone length.",
                    blocking=True,
                )
            )
        elif end_coordinate < start_coordinate:
            findings.append(
                _finding(
                    "replacement_end_before_start",
                    "error",
                    "InsertionSite",
                    "Replacement end coordinate must be greater than or equal to the start coordinate.",
                    blocking=True,
                )
            )
        else:
            replacement_start0, replacement_end0 = _interval_to_zero_based(start_coordinate, end_coordinate)
            removed_sequence = _text(backbone_asset.get("nucleotide_sequence"))[replacement_start0:replacement_end0]
            expected_removed = _normalize_whitespace_and_case(_text(insertion_site.get("expected_removed_sequence")))
            if expected_removed and expected_removed != removed_sequence:
                findings.append(
                    _finding(
                        "replacement_removed_sequence_mismatch",
                        "error",
                        "InsertionSite",
                        "Replacement mode expected removed sequence does not match the selected backbone interval.",
                        blocking=True,
                    )
                )

    return findings, {
        "topology": topology or "circular",
        "mode": mode,
        "cut_index": cut_index,
        "replacement_start0": replacement_start0,
        "replacement_end0": replacement_end0,
        "removed_sequence": removed_sequence,
        "insertion_orientation": _text(insertion_site.get("insertion_orientation")).lower() or "forward",
        "exact_insertion_contract": exact_contract,
    }


def _assemble_active_components(runtime: dict[str, Any]) -> dict[str, Any]:
    transcription_unit = _active_transcription_unit(runtime)
    if not transcription_unit:
        raise CanonicalConstructRuntimeError("Active TranscriptionUnit is not available.")
    component_index = _index_by(list(runtime.get("components") or []), "component_id")
    asset_index = _index_by(list(runtime.get("sequence_assets") or []), "asset_id")
    ordered_ids = [_text(item) for item in transcription_unit.get("ordered_component_ids") or [] if _text(item)]
    multi_tu = _multi_tu_assembly_context(runtime, ordered_ids, component_index)
    findings: list[dict[str, Any]] = list(multi_tu["findings"])
    assembled_fragments: list[str] = []
    feature_coordinates: list[dict[str, Any]] = []
    component_snapshots: list[dict[str, Any]] = []
    present_component_types: list[str] = []
    component_ranges: list[tuple[int, int]] = []
    cursor = 0
    cds_sequences: list[tuple[dict[str, Any], str]] = []

    type_ranks = {name: index for index, name in enumerate(COMPONENT_TYPE_ORDER)}
    last_rank = -1

    for component_id in ordered_ids:
        component = component_index.get(component_id)
        if component is None:
            findings.append(
                _finding(
                    "invalid_component_reference",
                    "error",
                    "TranscriptionUnit",
                    f"Component reference '{component_id}' is not present in the runtime payload.",
                    blocking=True,
                )
            )
            continue
        component_type = _text(component.get("component_type"))
        component_rank = type_ranks.get(component_type, -1)
        if not multi_tu["enabled"]:
            if component_rank < last_rank:
                findings.append(
                    _finding(
                        "unsupported_component_order",
                        "error",
                        f"Component:{component_id}",
                        f"Component order is not supported for single-gene assembly around '{component.get('display_name')}'.",
                        blocking=True,
                    )
                )
            else:
                last_rank = component_rank
        present_component_types.append(component_type)
        asset = asset_index.get(_text(component.get("sequence_asset_id")))
        component_snapshot = _build_component_snapshot(component, asset)
        unit_context = dict(multi_tu["component_context"].get(component_id) or {})
        if unit_context:
            component_snapshot.update(unit_context)
        component_snapshots.append(component_snapshot)
        if asset is None:
            findings.append(
                _finding(
                    "component_has_no_nucleotide_sequence",
                    "error",
                    f"Component:{component_id}",
                    f"Component '{component.get('display_name')}' has no linked SequenceAsset.",
                    blocking=True,
                )
            )
            continue
        asset_sequence = _text(asset.get("nucleotide_sequence")).upper()
        if _text(asset.get("molecule_type")).lower() == "protein":
            findings.append(
                _finding(
                    "protein_only_asset_used_as_dna",
                    "error",
                    f"Component:{component_id}",
                    f"Protein-only asset '{asset.get('display_name')}' cannot be assembled as construct DNA.",
                    blocking=True,
                )
            )
            findings.append(
                _finding(
                    "protein_only_asset_has_no_linked_nucleotide_asset",
                    "warning",
                    f"Component:{component_id}",
                    f"Protein-only asset '{asset.get('display_name')}' has no linked nucleotide asset for construct assembly.",
                    blocking=False,
                )
            )
            continue
        if not asset_sequence:
            findings.append(
                _finding(
                    "component_has_no_nucleotide_sequence",
                    "error",
                    f"Component:{component_id}",
                    f"Component '{component.get('display_name')}' does not contain nucleotide sequence content.",
                    blocking=True,
                )
            )
            continue
        invalid_dna_symbols = _contains_invalid_symbols(asset_sequence, CONSTRUCT_READY_DNA_ALPHABET)
        if invalid_dna_symbols:
            findings.append(
                _finding(
                    "illegal_nucleotide_symbol",
                    "error",
                    f"SequenceAsset:{asset.get('asset_id')}",
                    f"SequenceAsset '{asset.get('display_name')}' contains unsupported construct-ready DNA symbol(s): {', '.join(invalid_dna_symbols)}.",
                    blocking=True,
                )
            )
            continue
        strand = -1 if _text(component.get("orientation")).lower() == "reverse" else 1
        component_sequence = reverse_complement(asset_sequence) if strand == -1 else asset_sequence
        if strand == -1:
            findings.append(
                _finding(
                    "reverse_complement_orientation_used",
                    "warning",
                    f"Component:{component_id}",
                    f"Component '{component.get('display_name')}' uses reverse-complement orientation.",
                    blocking=False,
                )
            )
        if list(asset.get("warnings") or []):
            for warning_text in list(asset.get("warnings") or []):
                if "Unsupported imported feature detail" in str(warning_text):
                    findings.append(
                        _finding(
                            "unsupported_imported_feature_detail",
                            "warning",
                            f"SequenceAsset:{asset.get('asset_id')}",
                            "Unsupported imported feature detail was not fully represented.",
                            blocking=False,
                        )
                    )
                    break
        start = cursor
        end = cursor + len(component_sequence)
        if end <= start:
            findings.append(
                _finding(
                    "generated_feature_outside_final_sequence_bounds",
                    "error",
                    f"Component:{component_id}",
                    f"Generated coordinate range for '{component.get('display_name')}' is invalid.",
                    blocking=True,
                    affected_coordinate={"start": start, "end": end},
                )
            )
            continue
        if component_ranges and start < component_ranges[-1][1]:
            findings.append(
                _finding(
                    "generated_coordinate_overlap",
                    "error",
                    f"Component:{component_id}",
                    f"Generated coordinates overlap around '{component.get('display_name')}'.",
                    blocking=True,
                    affected_coordinate={"start": start, "end": end},
                )
            )
        component_ranges.append((start, end))
        assembled_fragments.append(component_sequence)
        feature = {
            "component_id": component_id,
            "source_asset_id": _text(asset.get("asset_id")),
            "name": _text(component.get("display_name")) or _text(asset.get("display_name")),
            "component_type": component_type,
            "start": start,
            "end": end,
            "strand": strand,
        }
        if unit_context:
            feature.update(
                {
                    "unit_id": unit_context["unit_id"],
                    "unit_name": unit_context["unit_name"],
                    "unit_order": unit_context["unit_order"],
                    "biological_role": unit_context["biological_role"],
                }
            )
        feature_coordinates.append(feature)
        if component_type == "cds":
            validation_sequence = asset_sequence if unit_context.get("unit_orientation") == "reverse" else component_sequence
            cds_sequences.append((component, validation_sequence))
        cursor = end

    final_sequence = "".join(assembled_fragments)
    if not multi_tu["enabled"]:
        for required_component_type in COMPONENT_TYPE_ORDER:
            if required_component_type in MANDATORY_COMPONENT_TYPES and required_component_type not in present_component_types:
                findings.append(
                    _finding(
                        f"missing_{required_component_type}",
                        "error",
                        "TranscriptionUnit",
                        f"Required component type '{required_component_type}' is missing from the active transcription unit.",
                        blocking=True,
                    )
                )

    for component, cds_sequence in cds_sequences:
        if len(cds_sequence) % 3 != 0:
            findings.append(
                _finding(
                    "cds_length_not_divisible_by_three",
                    "error",
                    f"Component:{component.get('component_id')}",
                    f"CDS '{component.get('display_name')}' length is not divisible by three.",
                    blocking=True,
                )
            )
        protein = translate(cds_sequence)
        if not cds_sequence.startswith("ATG"):
            findings.append(
                _finding(
                    "cds_missing_start_codon",
                    "warning",
                    f"Component:{component.get('component_id')}",
                    f"CDS '{component.get('display_name')}' does not start with ATG.",
                    blocking=False,
                )
            )
        if cds_sequence[-3:] not in {"TAA", "TAG", "TGA"}:
            findings.append(
                _finding(
                    "cds_missing_terminal_stop_codon",
                    "warning",
                    f"Component:{component.get('component_id')}",
                    f"CDS '{component.get('display_name')}' does not end with a terminal stop codon.",
                    blocking=False,
                )
            )
        if "*" in protein[:-1]:
            findings.append(
                _finding(
                    "internal_in_frame_stop_codon",
                    "error",
                    f"Component:{component.get('component_id')}",
                    f"CDS '{component.get('display_name')}' contains an internal in-frame stop codon.",
                    blocking=True,
                )
            )

    if multi_tu["enabled"]:
        component_features = {
            _text(feature.get("component_id")): feature
            for feature in feature_coordinates
            if _text(feature.get("component_id"))
        }
        unit_ranges: list[tuple[int, int, str]] = []
        for unit in multi_tu["ordered_units"]:
            unit_id = _text(unit.get("unit_id"))
            role_features = [
                component_features.get(_multi_tu_component_id(unit, role))
                for role, _component_type, required in _multi_tu_role_specs(unit)
                if required
            ]
            if any(feature is None for feature in role_features):
                continue
            all_unit_features = [
                component_features.get(_multi_tu_component_id(unit, role))
                for role, _component_type, _required in _multi_tu_role_specs(unit)
                if _multi_tu_component_id(unit, role)
            ]
            starts = [int(feature.get("start", 0)) for feature in all_unit_features if feature]
            ends = [int(feature.get("end", 0)) for feature in all_unit_features if feature]
            unit_start, unit_end = min(starts), max(ends)
            if unit_ranges and unit_start < unit_ranges[-1][1]:
                findings.append(
                    _finding(
                        "multi_tu_unit_overlap",
                        "error",
                        f"ExpressionUnit:{unit_id}",
                        f"Expression unit '{unit_id}' overlaps expression unit '{unit_ranges[-1][2]}'.",
                        blocking=True,
                    )
                )
            unit_ranges.append((unit_start, unit_end, unit_id))
            feature_coordinates.append(
                {
                    "component_id": "",
                    "source_asset_id": "",
                    "unit_id": unit_id,
                    "unit_name": _text(unit.get("unit_name")) or unit_id,
                    "unit_order": int(unit.get("order", 0) or 0),
                    "name": _text(unit.get("unit_name")) or unit_id,
                    "component_type": "transcription_unit",
                    "start": unit_start,
                    "end": unit_end,
                    "strand": -1 if _text(unit.get("orientation")).lower() == "reverse" else 1,
                }
            )

    for feature in feature_coordinates:
        if int(feature.get("start", 0)) < 0 or int(feature.get("end", 0)) > len(final_sequence):
            findings.append(
                _finding(
                    "generated_feature_outside_final_sequence_bounds",
                    "error",
                    f"Component:{feature.get('component_id')}",
                    f"Generated feature '{feature.get('name')}' falls outside the final sequence bounds.",
                    blocking=True,
                    affected_coordinate={"start": int(feature.get("start", 0)), "end": int(feature.get("end", 0))},
                )
            )

    input_signature_payload: Any = component_snapshots
    if multi_tu["enabled"]:
        input_signature_payload = {
            "project_type": MULTI_TU_PROJECT_TYPE,
            "expression_units": multi_tu["ordered_units"],
            "components": component_snapshots,
        }
    return {
        "final_sequence": final_sequence,
        "feature_coordinates": feature_coordinates,
        "validation_findings": findings,
        "input_signature": _checksum_payload(input_signature_payload),
        "translation": translate(cds_sequences[0][1]) if cds_sequences else "",
    }


def _build_validation_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    blocking_count = sum(1 for item in findings if bool(item.get("blocking")))
    warning_count = sum(1 for item in findings if _text(item.get("severity")).lower() == "warning")
    info_count = sum(1 for item in findings if _text(item.get("severity")).lower() == "info")
    return {
        "blocking_count": blocking_count,
        "warning_count": warning_count,
        "info_count": info_count,
    }


def generate_active_construct(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    project_id = _text((runtime_payload or {}).get("project_id"))
    runtime = ensure_runtime(project_id, runtime_payload)
    assembled = _assemble_active_components(runtime)
    duplicate_findings = _duplicate_id_findings(runtime)
    findings = [*duplicate_findings, *assembled["validation_findings"]]
    checksum = seq_hash(assembled["final_sequence"])
    transcription_unit = _active_transcription_unit(runtime)
    construct = _active_construct(runtime)
    if not transcription_unit or not construct:
        raise CanonicalConstructRuntimeError("Active runtime objects are not available.")
    revision_id = _revision_id(checksum, assembled["input_signature"]) if assembled["final_sequence"] else ""
    transcription_unit.update(
        {
            "generated_nucleotide_sequence": assembled["final_sequence"],
            "generated_sequence_checksum": checksum,
            "feature_coordinates": assembled["feature_coordinates"],
            "validation_findings": findings,
            "revision_id": revision_id,
            "generated_at": _timestamp(),
            "stale": False,
            "input_signature": assembled["input_signature"],
            "translation": assembled["translation"],
        }
    )
    summary = _build_validation_summary(findings)
    construct_status = "current"
    if summary["blocking_count"] > 0:
        construct_status = "blocking_invalid"
    construct.update(
        {
            "transcription_unit_id": _text(transcription_unit.get("tu_id")),
            "current_revision": revision_id,
            "construct_status": construct_status,
            "canonical_generated_sequence": assembled["final_sequence"],
            "validation_summary": summary,
            "sequence_checksum": checksum,
            "persistence_identity": _text(construct.get("construct_id")),
            "export_identity": {
                "fasta_filename": f"{_text(construct.get('construct_id'))}_{revision_id}.fasta" if revision_id else "",
                "genbank_filename": f"{_text(construct.get('construct_id'))}_{revision_id}.gb" if revision_id else "",
            },
            "input_signature": assembled["input_signature"],
        }
    )
    return runtime


def _assemble_complete_plasmid(runtime: dict[str, Any]) -> dict[str, Any]:
    transcription_unit = _active_transcription_unit(runtime)
    construct = _active_construct(runtime)
    complete_plasmid = _active_complete_plasmid(runtime)
    insertion_site = _active_insertion_site(runtime)
    if not transcription_unit or not construct or not complete_plasmid:
        raise CanonicalConstructRuntimeError("Active canonical construct runtime objects are not available.")

    findings = _duplicate_id_findings(runtime)
    construct_status = _text(construct.get("construct_status"))
    if not _text(transcription_unit.get("generated_nucleotide_sequence")):
        findings.append(
            _finding(
                "invalid_or_missing_transcription_unit",
                "error",
                f"Construct:{construct.get('construct_id')}",
                "Generate the canonical transcription unit before complete plasmid generation.",
                blocking=True,
            )
        )
    elif construct_status == "stale":
        findings.append(
            _finding(
                "stale_transcription_unit",
                "error",
                f"Construct:{construct.get('construct_id')}",
                "The canonical transcription unit is stale and must be regenerated before complete plasmid generation.",
                blocking=True,
            )
        )
    elif construct_status == "blocking_invalid":
        findings.append(
            _finding(
                "invalid_or_missing_transcription_unit",
                "error",
                f"Construct:{construct.get('construct_id')}",
                "Blocking findings remain on the canonical transcription unit.",
                blocking=True,
            )
        )

    asset_index = _index_by(list(runtime.get("sequence_assets") or []), "asset_id")
    backbone_asset = asset_index.get(_text(insertion_site.get("backbone_asset_id")) or _text(complete_plasmid.get("backbone_asset_id")), {})
    site_findings, site_state = _validate_insertion_site_against_backbone(insertion_site, backbone_asset)
    findings.extend(site_findings)

    cassette_sequence = _text(transcription_unit.get("generated_nucleotide_sequence"))
    insertion_orientation = _text(site_state.get("insertion_orientation")).lower() or "forward"
    if insertion_orientation == "reverse":
        cassette_sequence = reverse_complement(cassette_sequence)
    backbone_sequence = _text(backbone_asset.get("nucleotide_sequence"))
    imported_backbone_features = list(backbone_asset.get("imported_feature_records") or [])
    supported_backbone_features: list[dict[str, Any]] = []
    for feature in imported_backbone_features:
        if bool(feature.get("unsupported_location")):
            findings.append(
                _finding(
                    "unsupported_backbone_feature_location",
                    "error",
                    f"SequenceAsset:{backbone_asset.get('asset_id')}",
                    f"Imported backbone feature '{_feature_label(feature)}' uses an unsupported compound or cross-origin location.",
                    blocking=True,
                )
            )
            continue
        supported_backbone_features.append(feature)

    combined_features: list[dict[str, Any]] = []
    shifted_backbone_features: list[dict[str, Any]] = []
    inserted_features: list[dict[str, Any]] = []
    final_sequence = ""
    cassette_span: dict[str, int] = {}

    if not any(item.get("blocking") for item in findings):
        if site_state["mode"] == "insertion":
            cut_index = int(site_state["cut_index"])
            exact_contract = dict(site_state.get("exact_insertion_contract") or {})
            if exact_contract:
                try:
                    final_sequence = insert_pcambia1300_cassette(
                        backbone_sequence,
                        cassette_sequence,
                        accession_version=exact_contract["accession_version"],
                        circular=bool(exact_contract["circular"]),
                    )
                except Pcambia1300ExactInsertionContractError as exc:
                    findings.append(
                        _finding(
                            "pcambia1300_exact_insertion_output_invalid",
                            "error",
                            "CompletePlasmid",
                            str(exc),
                            blocking=True,
                        )
                    )
            else:
                for feature in supported_backbone_features:
                    if not _is_record_source_feature(feature) and _feature_crosses_insertion_boundary(feature, cut_index):
                        findings.append(
                            _finding(
                                "overlapping_backbone_feature_conflict",
                                "error",
                                f"BackboneFeature:{_text(feature.get('feature_id'))}",
                                f"Backbone feature '{_feature_label(feature)}' overlaps the selected insertion boundary.",
                                blocking=True,
                            )
                        )
                final_sequence = backbone_sequence[:cut_index] + cassette_sequence + backbone_sequence[cut_index:]
            cassette_span = {"start": cut_index, "end": cut_index + len(cassette_sequence)}
            remapped_features = (
                remap_pcambia1300_features(
                    supported_backbone_features,
                    cassette_length=len(cassette_sequence),
                )
                if exact_contract
                else [
                    _shift_feature_after_boundary(
                        feature,
                        boundary=cut_index,
                        delta=len(cassette_sequence),
                    )
                    for feature in supported_backbone_features
                ]
            )
            for feature in remapped_features:
                shifted = _deepcopy(feature)
                shifted["feature_type"] = _text(shifted.get("type")) or "misc_feature"
                shifted["source"] = "backbone"
                shifted["backbone_feature_id"] = _text(feature.get("feature_id"))
                shifted_backbone_features.append(shifted)
        else:
            replacement_start0 = int(site_state["replacement_start0"])
            replacement_end0 = int(site_state["replacement_end0"])
            for feature in supported_backbone_features:
                if not _is_record_source_feature(feature) and _feature_overlaps_interval(
                    feature, replacement_start0, replacement_end0
                ):
                    findings.append(
                        _finding(
                            "overlapping_backbone_feature_conflict",
                            "error",
                            f"BackboneFeature:{_text(feature.get('feature_id'))}",
                            f"Backbone feature '{_feature_label(feature)}' overlaps the selected replacement interval.",
                            blocking=True,
                        )
                    )
            removed_length = max(0, replacement_end0 - replacement_start0)
            delta = len(cassette_sequence) - removed_length
            final_sequence = backbone_sequence[:replacement_start0] + cassette_sequence + backbone_sequence[replacement_end0:]
            cassette_span = {"start": replacement_start0, "end": replacement_start0 + len(cassette_sequence)}
            for feature in supported_backbone_features:
                shifted = _shift_feature_after_boundary(
                    feature,
                    boundary=replacement_end0,
                    delta=delta,
                )
                shifted["feature_type"] = _text(shifted.get("type")) or "misc_feature"
                shifted["source"] = "backbone"
                shifted["backbone_feature_id"] = _text(feature.get("feature_id"))
                shifted_backbone_features.append(shifted)

    if not any(item.get("blocking") for item in findings) and cassette_span:
        original_cassette_length = len(_text(transcription_unit.get("generated_nucleotide_sequence")))
        for feature in list(transcription_unit.get("feature_coordinates") or []):
            inserted = _deepcopy(feature)
            if insertion_orientation == "reverse":
                inserted["start"] = cassette_span["start"] + original_cassette_length - int(feature.get("end", 0))
                inserted["end"] = cassette_span["start"] + original_cassette_length - int(feature.get("start", 0))
                inserted["strand"] = -int(feature.get("strand", 1) or 1)
            else:
                inserted["start"] = cassette_span["start"] + int(feature.get("start", 0))
                inserted["end"] = cassette_span["start"] + int(feature.get("end", 0))
            inserted["feature_type"] = (
                "misc_feature"
                if _text(feature.get("component_type")) == "transcription_unit"
                else (_text(feature.get("component_type")) or "misc_feature")
            )
            inserted["source"] = (
                "multi_tu_unit"
                if _text(feature.get("component_type")) == "transcription_unit"
                else "transcription_unit"
            )
            inserted["qualifiers"] = {
                "label": [_text(feature.get("name"))],
                "component_id": [_text(feature.get("component_id"))],
                "source_asset_id": [_text(feature.get("source_asset_id"))],
                "traceability": [
                    f"Derived from R227 component {_text(feature.get('component_id'))} and asset {_text(feature.get('source_asset_id'))}."
                ],
            }
            if _text(feature.get("unit_id")):
                inserted["qualifiers"]["unit_id"] = [_text(feature.get("unit_id"))]
                inserted["qualifiers"]["unit_order"] = [str(int(feature.get("unit_order", 0) or 0))]
            if _text(feature.get("biological_role")):
                inserted["qualifiers"]["biological_role"] = [_text(feature.get("biological_role"))]
            inserted_features.append(inserted)
        if dict(site_state.get("exact_insertion_contract") or {}):
            contract = exact_insertion_contract()
            inserted_features.extend(
                [
                    {
                        "name": "AF234296.1 inserted cassette source",
                        "label": "AF234296.1 inserted cassette source",
                        "feature_type": "source",
                        "source": "exact_insertion_contract",
                        "start": cassette_span["start"],
                        "end": cassette_span["end"],
                        "strand": 1,
                        "qualifiers": {
                            "label": ["AF234296.1 inserted cassette source"],
                            "asset_id": [contract["asset_id"]],
                            "contract_version": [contract["contract_version"]],
                        },
                    },
                    {
                        "name": "Inserted single-gene transcription unit",
                        "label": "Inserted single-gene transcription unit",
                        "feature_type": "misc_feature",
                        "component_type": "transcription_unit",
                        "biological_role": "transcription_unit",
                        "source": "exact_insertion_contract",
                        "start": cassette_span["start"],
                        "end": cassette_span["end"],
                        "strand": 1,
                        "qualifiers": {
                            "label": ["Inserted single-gene transcription unit"],
                            "biological_role": ["transcription_unit"],
                            "contract_version": [contract["contract_version"]],
                        },
                    },
                ]
            )
        combined_features = sorted(
            [*shifted_backbone_features, *inserted_features],
            key=lambda item: (int(item.get("start", 0)), int(item.get("end", 0)), _feature_label(item)),
        )

    for feature in combined_features:
        parts = list(feature.get("location_parts") or [])
        if not parts:
            parts = [{"start": feature.get("start", 0), "end": feature.get("end", 0)}]
        if any(
            int(part.get("start", 0)) < 0
            or int(part.get("end", 0)) > len(final_sequence)
            or int(part.get("end", 0)) <= int(part.get("start", 0))
            for part in parts
        ):
            findings.append(
                _finding(
                    "feature_coordinate_corruption",
                    "error",
                    f"Feature:{_feature_label(feature)}",
                    f"Feature '{_feature_label(feature)}' falls outside the generated complete plasmid bounds.",
                    blocking=True,
                )
            )

    input_signature = _checksum_payload(
        {
            "transcription_unit_revision": _text(transcription_unit.get("revision_id")),
            "transcription_unit_checksum": _text(transcription_unit.get("generated_sequence_checksum")),
            "backbone_asset_signature": _asset_feature_signature(backbone_asset),
            "insertion_site": {
                "site_id": _text(insertion_site.get("site_id")),
                "backbone_asset_id": _text(insertion_site.get("backbone_asset_id")),
                "start_coordinate": int(insertion_site.get("start_coordinate", 0) or 0),
                "end_coordinate": int(insertion_site.get("end_coordinate", 0) or 0),
                "mode": _text(insertion_site.get("mode")),
                "expected_removed_sequence": _text(insertion_site.get("expected_removed_sequence")),
                "insertion_orientation": insertion_orientation,
                "user_confirmation_state": _text(insertion_site.get("user_confirmation_state")),
                "backbone_topology_confirmation_state": _text(insertion_site.get("backbone_topology_confirmation_state")),
                "workflow_id": _text(insertion_site.get("workflow_id")),
                "exact_insertion_contract": dict(insertion_site.get("exact_insertion_contract") or {}),
            },
        }
    )
    return {
        "final_sequence": final_sequence,
        "sequence_checksum": seq_hash(final_sequence),
        "topology": site_state.get("topology", "circular"),
        "backbone_feature_coordinates": shifted_backbone_features,
        "inserted_feature_coordinates": inserted_features,
        "combined_feature_coordinates": combined_features,
        "cassette_coordinate_span": cassette_span,
        "validation_findings": findings,
        "validation_summary": _build_validation_summary(findings),
        "input_signature": input_signature,
        "backbone_asset_id": _text(backbone_asset.get("asset_id")),
        "insertion_site_id": _text(insertion_site.get("site_id")),
    }


def generate_active_complete_plasmid(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    runtime = ensure_runtime(_text((runtime_payload or {}).get("project_id")), runtime_payload)
    complete_plasmid = _active_complete_plasmid(runtime)
    transcription_unit = _active_transcription_unit(runtime)
    if not complete_plasmid or not transcription_unit:
        raise CanonicalConstructRuntimeError("Active complete plasmid runtime objects are not available.")

    assembled = _assemble_complete_plasmid(runtime)
    revision_id = _revision_id(assembled["sequence_checksum"], assembled["input_signature"]) if assembled["final_sequence"] else ""
    status = "current"
    if int(assembled["validation_summary"]["blocking_count"]) > 0:
        status = "blocking_invalid"
    complete_plasmid.update(
        {
            "transcription_unit_id": _text(transcription_unit.get("tu_id")),
            "backbone_asset_id": assembled["backbone_asset_id"],
            "insertion_site_id": assembled["insertion_site_id"],
            "generated_nucleotide_sequence": assembled["final_sequence"],
            "sequence_checksum": assembled["sequence_checksum"],
            "topology": assembled["topology"] or "circular",
            "backbone_feature_coordinates": assembled["backbone_feature_coordinates"],
            "inserted_feature_coordinates": assembled["inserted_feature_coordinates"],
            "combined_feature_coordinates": assembled["combined_feature_coordinates"],
            "validation_findings": assembled["validation_findings"],
            "validation_summary": assembled["validation_summary"],
            "cassette_coordinate_span": assembled["cassette_coordinate_span"],
            "current_revision": revision_id,
            "generated_at": _timestamp(),
            "construct_status": status,
            "export_identity": {
                "fasta_filename": f"{_text(complete_plasmid.get('plasmid_id'))}_{revision_id}.fasta" if revision_id else "",
                "genbank_filename": f"{_text(complete_plasmid.get('plasmid_id'))}_{revision_id}.gb" if revision_id else "",
            },
            "input_signature": assembled["input_signature"],
        }
    )
    insertion_site = _active_insertion_site(runtime)
    if insertion_site:
        insertion_site["validation_state"] = status
    return runtime


def _validate_active_complete_plasmid_state(runtime: dict[str, Any]) -> dict[str, Any]:
    complete_plasmid = _active_complete_plasmid(runtime)
    if not complete_plasmid:
        return runtime
    stored_sequence = _text(complete_plasmid.get("generated_nucleotide_sequence"))
    if not stored_sequence:
        return runtime

    regenerated = _assemble_complete_plasmid(runtime)
    findings = list(regenerated["validation_findings"])
    if _text(complete_plasmid.get("sequence_checksum")) and _text(complete_plasmid.get("sequence_checksum")) != regenerated["sequence_checksum"]:
        findings.append(
            _finding(
                "complete_plasmid_checksum_mismatch",
                "error",
                f"Plasmid:{complete_plasmid.get('plasmid_id')}",
                "Persisted complete plasmid checksum differs from the regenerated checksum.",
                blocking=True,
            )
        )
    if stored_sequence != regenerated["final_sequence"] or _text(complete_plasmid.get("input_signature")) != regenerated["input_signature"]:
        findings.append(
            _finding(
                "stale_complete_plasmid_after_source_change",
                "error",
                f"Plasmid:{complete_plasmid.get('plasmid_id')}",
                "Complete plasmid output is stale after a cassette, backbone, or insertion-site change.",
                blocking=True,
            )
        )
    if list(complete_plasmid.get("combined_feature_coordinates") or []) and list(complete_plasmid.get("combined_feature_coordinates") or []) != regenerated["combined_feature_coordinates"]:
        findings.append(
            _finding(
                "corrupted_persisted_complete_plasmid_feature_coordinate",
                "error",
                f"Plasmid:{complete_plasmid.get('plasmid_id')}",
                "Persisted complete plasmid feature coordinates differ from the regenerated canonical model.",
                blocking=True,
            )
        )

    summary = _build_validation_summary(findings)
    status = "current"
    if any(item.get("rule_id") == "stale_complete_plasmid_after_source_change" for item in findings):
        status = "stale"
    elif summary["blocking_count"] > 0:
        status = "blocking_invalid"

    complete_plasmid["validation_findings"] = findings
    complete_plasmid["validation_summary"] = summary
    complete_plasmid["construct_status"] = status
    insertion_site = _active_insertion_site(runtime)
    if insertion_site:
        insertion_site["validation_state"] = status
    return runtime


def validate_active_runtime(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    project_id = _text((runtime_payload or {}).get("project_id"))
    runtime = ensure_runtime(project_id, runtime_payload)
    duplicate_findings = _duplicate_id_findings(runtime)
    assembled = _assemble_active_components(runtime)
    transcription_unit = _active_transcription_unit(runtime)
    construct = _active_construct(runtime)
    if not transcription_unit or not construct:
        raise CanonicalConstructRuntimeError("Active runtime objects are not available.")

    findings = [*duplicate_findings, *assembled["validation_findings"]]
    stored_sequence = _text(transcription_unit.get("generated_nucleotide_sequence"))
    stored_checksum = _text(transcription_unit.get("generated_sequence_checksum")) or _text(construct.get("sequence_checksum"))
    regenerated_checksum = seq_hash(assembled["final_sequence"])
    if stored_sequence:
        if stored_checksum and stored_checksum != regenerated_checksum:
            findings.append(
                _finding(
                    "persisted_checksum_differs_from_regenerated_checksum",
                    "error",
                    f"Construct:{construct.get('construct_id')}",
                    "Persisted checksum differs from the regenerated checksum for the current component state.",
                    blocking=True,
                )
            )
        if stored_sequence != assembled["final_sequence"] or _text(transcription_unit.get("input_signature")) != assembled["input_signature"]:
            findings.append(
                _finding(
                    "stale_generated_output_after_source_sequence_modification",
                    "error",
                    f"Construct:{construct.get('construct_id')}",
                    "Generated output is stale after a source sequence, order, or orientation change.",
                    blocking=True,
                )
            )
        stored_features = list(transcription_unit.get("feature_coordinates") or [])
        if stored_features and stored_features != assembled["feature_coordinates"]:
            findings.append(
                _finding(
                    "corrupted_persisted_coordinate",
                    "error",
                    f"Construct:{construct.get('construct_id')}",
                    "Persisted feature coordinates differ from the regenerated coordinate model.",
                    blocking=True,
                )
            )

    summary = _build_validation_summary(findings)
    construct_status = "current"
    if any(item.get("rule_id") == "stale_generated_output_after_source_sequence_modification" for item in findings):
        construct_status = "stale"
    elif summary["blocking_count"] > 0:
        construct_status = "blocking_invalid"

    transcription_unit["validation_findings"] = findings
    transcription_unit["translation"] = assembled["translation"]
    transcription_unit["stale"] = construct_status == "stale"
    construct["validation_summary"] = summary
    construct["construct_status"] = construct_status
    return _validate_active_complete_plasmid_state(runtime)


def component_rows(runtime_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    runtime = ensure_runtime(_text((runtime_payload or {}).get("project_id")), runtime_payload)
    asset_index = _index_by(list(runtime.get("sequence_assets") or []), "asset_id")
    rows: list[dict[str, Any]] = []
    for component in list(runtime.get("components") or []):
        asset = asset_index.get(_text(component.get("sequence_asset_id")), {})
        rows.append(
            {
                "component_id": _text(component.get("component_id")),
                "display_name": _text(component.get("display_name")),
                "component_type": _text(component.get("component_type")),
                "orientation": _text(component.get("orientation")),
                "sequence_asset_id": _text(component.get("sequence_asset_id")),
                "asset_name": _text(asset.get("display_name")),
                "asset_length": int(asset.get("length", 0) or 0),
                "molecule_type": _text(asset.get("molecule_type")),
                "provenance_reference": _text(component.get("provenance_reference")),
                "created_at": _text(component.get("created_at")),
            }
        )
    return rows


def active_construct_snapshot(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    runtime = validate_active_runtime(runtime_payload)
    transcription_unit = _active_transcription_unit(runtime)
    construct = _active_construct(runtime)
    findings = list(transcription_unit.get("validation_findings") or [])
    generated_sequence = _text(transcription_unit.get("generated_nucleotide_sequence"))
    return {
        "runtime": runtime,
        "construct_id": _text(construct.get("construct_id")),
        "construct_status": _text(construct.get("construct_status")) or "draft",
        "revision_id": _text(transcription_unit.get("revision_id")),
        "sequence": generated_sequence,
        "sequence_length": len(generated_sequence),
        "sequence_checksum": _text(construct.get("sequence_checksum")) or _text(transcription_unit.get("generated_sequence_checksum")),
        "translation": _text(transcription_unit.get("translation")),
        "feature_rows": _feature_rows_for_display(list(transcription_unit.get("feature_coordinates") or [])),
        "validation_findings": findings,
        "validation_summary": _deepcopy(construct.get("validation_summary") or {}),
        "ordered_component_ids": list(transcription_unit.get("ordered_component_ids") or []),
    }


def active_complete_plasmid_snapshot(runtime_payload: dict[str, Any] | None) -> dict[str, Any]:
    runtime = validate_active_runtime(runtime_payload)
    complete_plasmid = _active_complete_plasmid(runtime)
    insertion_site = _active_insertion_site(runtime)
    if not complete_plasmid:
        raise CanonicalConstructRuntimeError("Active complete plasmid construct is not available.")
    sequence = _text(complete_plasmid.get("generated_nucleotide_sequence"))
    cassette_span = complete_plasmid.get("cassette_coordinate_span") if isinstance(complete_plasmid.get("cassette_coordinate_span"), dict) else {}
    cassette_display = {}
    if cassette_span:
        cassette_display = {
            "start": int(cassette_span.get("start", 0) or 0) + 1,
            "end": int(cassette_span.get("end", 0) or 0),
        }
    return {
        "runtime": runtime,
        "plasmid_id": _text(complete_plasmid.get("plasmid_id")),
        "construct_status": _text(complete_plasmid.get("construct_status")) or "draft",
        "revision_id": _text(complete_plasmid.get("current_revision")),
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_checksum": _text(complete_plasmid.get("sequence_checksum")),
        "topology": _text(complete_plasmid.get("topology")) or "circular",
        "cassette_coordinates": cassette_display,
        "feature_rows": _complete_feature_rows_for_display(list(complete_plasmid.get("combined_feature_coordinates") or [])),
        "validation_findings": list(complete_plasmid.get("validation_findings") or []),
        "validation_summary": _deepcopy(complete_plasmid.get("validation_summary") or {}),
        "backbone_asset_id": _text(complete_plasmid.get("backbone_asset_id")),
        "insertion_site": _deepcopy(insertion_site),
    }


def export_active_construct(runtime_payload: dict[str, Any] | None, *, project_name: str) -> dict[str, Any]:
    snapshot = active_construct_snapshot(runtime_payload)
    if int((snapshot.get("validation_summary") or {}).get("blocking_count", 0) or 0) > 0:
        raise CanonicalConstructRuntimeError("Blocking-invalid constructs cannot be exported.")
    if _text(snapshot.get("construct_status")) == "stale":
        raise CanonicalConstructRuntimeError("Stale constructs must be regenerated before export.")
    if not _text(snapshot.get("sequence")):
        raise CanonicalConstructRuntimeError("No generated construct sequence is available for export.")

    from components.export_manager import generate_fasta_string, generate_genbank_string

    sequence = _text(snapshot.get("sequence"))
    construct_label = _text(snapshot.get("construct_id")) or "construct"
    revision = _text(snapshot.get("revision_id")) or "unversioned"
    checksum = _text(snapshot.get("sequence_checksum"))
    safe_label = f"{construct_label}|rev={revision}|len={len(sequence)}|sha256={checksum}"
    export_features = []
    runtime = snapshot["runtime"]
    transcription_unit = _active_transcription_unit(runtime)
    for feature in list(transcription_unit.get("feature_coordinates") or []):
        display_start, display_end = _display_interval(int(feature.get("start", 0)), int(feature.get("end", 0)))
        component_type = _text(feature.get("component_type"))
        export_type = "misc_feature" if component_type == "transcription_unit" else (component_type or "misc_feature")
        if _text(feature.get("unit_id")) and len(export_type) > 15:
            export_type = "misc_feature"
        export_feature = {
            "name": _text(feature.get("name")),
            "label": _text(feature.get("name")),
            "type": export_type,
            "start": display_start,
            "end": display_end,
            "strand": int(feature.get("strand", 1) or 1),
            "component_id": _text(feature.get("component_id")),
            "source_asset_id": _text(feature.get("source_asset_id")),
        }
        if _text(feature.get("unit_id")):
            export_feature["qualifiers"] = {
                "unit_id": [_text(feature.get("unit_id"))],
                "unit_order": [str(int(feature.get("unit_order", 0) or 0))],
            }
            if _text(feature.get("biological_role")):
                export_feature["qualifiers"]["biological_role"] = [_text(feature.get("biological_role"))]
        export_features.append(export_feature)
    from services.single_gene_assisted_components import single_gene_assisted_export_features

    export_features = single_gene_assisted_export_features(runtime, export_features)
    return {
        "fasta": {
            "label": "Export canonical FASTA (.fasta)",
            "file_name": f"{construct_label}_{revision}.fasta",
            "mime": "text/plain",
            "data": generate_fasta_string(sequence, safe_label),
        },
        "genbank": {
            "label": "Export canonical GenBank (.gb)",
            "file_name": f"{construct_label}_{revision}.gb",
            "mime": "text/plain",
            "data": generate_genbank_string(
                sequence,
                export_features,
                project_name or construct_label,
                topology="linear",
            ),
        },
        "metadata": {
            "construct_id": construct_label,
            "revision_id": revision,
            "sequence_length": len(sequence),
            "sequence_checksum": checksum,
            "features": export_features,
        },
    }


def export_active_complete_plasmid(runtime_payload: dict[str, Any] | None, *, project_name: str) -> dict[str, Any]:
    snapshot = active_complete_plasmid_snapshot(runtime_payload)
    if int((snapshot.get("validation_summary") or {}).get("blocking_count", 0) or 0) > 0:
        raise CanonicalConstructRuntimeError("Blocking-invalid complete plasmids cannot be exported.")
    if _text(snapshot.get("construct_status")) == "stale":
        raise CanonicalConstructRuntimeError("Stale complete plasmids must be regenerated before export.")
    if not _text(snapshot.get("sequence")):
        raise CanonicalConstructRuntimeError("No generated complete plasmid sequence is available for export.")

    from Bio import SeqIO
    from components.export_manager import generate_fasta_string, generate_genbank_string

    sequence = _text(snapshot.get("sequence"))
    checksum = _text(snapshot.get("sequence_checksum"))
    stable_record_id = f"complete_plasmid_{checksum[:16]}"
    safe_label = f"{stable_record_id}|len={len(sequence)}|sha256={checksum}"
    runtime = snapshot["runtime"]
    complete_plasmid = _active_complete_plasmid(runtime)
    from services.single_gene_assisted_components import single_gene_assisted_export_features

    export_features = _stable_complete_plasmid_export_features(
        single_gene_assisted_export_features(runtime, list(complete_plasmid.get("combined_feature_coordinates") or [])),
        list(runtime.get("sequence_assets") or []),
    )
    fasta_text = generate_fasta_string(sequence, safe_label)
    genbank_text = generate_genbank_string(
        sequence,
        export_features,
        stable_record_id,
        topology=_text(snapshot.get("topology")) or "circular",
    )
    record = next(SeqIO.parse(StringIO(genbank_text), "genbank"))
    roundtrip_sequence = _normalize_whitespace_and_case(str(record.seq))
    if roundtrip_sequence != sequence:
        raise CanonicalConstructRuntimeError("Exported GenBank sequence differs from the canonical complete plasmid sequence.")
    roundtrip_topology = _normalize_topology(record.annotations.get("topology")) or "circular"
    if roundtrip_topology != (_text(snapshot.get("topology")) or "circular"):
        raise CanonicalConstructRuntimeError("Exported GenBank topology differs from the canonical complete plasmid topology.")

    critical_features = [
        (
            _text(item.get("type")),
            _text(item.get("name")),
            int(item.get("strand", 1) or 1),
            tuple(
                sorted(
                    (
                        int(part.get("start", 0) or 0),
                        int(part.get("end", 0) or 0),
                        int(part.get("strand", item.get("strand", 1)) or 1),
                    )
                    for part in (
                        list(item.get("location_parts") or [])
                        or [{"start": item.get("start", 0), "end": item.get("end", 0), "strand": item.get("strand", 1)}]
                    )
                )
            ),
        )
        for item in export_features
    ]
    roundtrip_features = [
        (
            _text(feature.type),
            _text((feature.qualifiers or {}).get("label", [""])[0]),
            int(feature.location.strand or 1),
            tuple(
                sorted(
                    (
                        int(part.start) + 1,
                        int(part.end),
                        int(part.strand or feature.location.strand or 1),
                    )
                    for part in list(getattr(feature.location, "parts", None) or [feature.location])
                )
            ),
        )
        for feature in list(record.features or [])
    ]
    if critical_features != roundtrip_features:
        raise CanonicalConstructRuntimeError("Exported GenBank critical features differ from the canonical complete plasmid feature set.")

    return {
        "fasta": {
            "label": "Export complete plasmid FASTA (.fasta)",
            "file_name": f"{stable_record_id}.fasta",
            "mime": "text/plain",
            "data": fasta_text,
        },
        "genbank": {
            "label": "Export complete plasmid GenBank (.gb)",
            "file_name": f"{stable_record_id}.gb",
            "mime": "text/plain",
            "data": genbank_text,
        },
        "metadata": {
            "record_id": stable_record_id,
            "sequence_length": len(sequence),
            "sequence_checksum": checksum,
            "topology": _text(snapshot.get("topology")) or "circular",
            "features": export_features,
        },
    }
