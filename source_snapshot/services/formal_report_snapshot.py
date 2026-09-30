"""Pure, deterministic facts for documentation-only AI report drafts.

This module deliberately has no dependency on Streamlit, persistence, or
runtime construction services.  Callers pass their already-derived facts in;
the builders retain only a small, reviewable subset of those facts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


SNAPSHOT_SCHEMA_VERSION = "formal-report-snapshot-v1"
WORKFLOW_TYPES = frozenset({"single_gene", "multi_tu", "pathway"})
_COMPONENT_RECORD_FIELDS = frozenset(
    {
        "order",
        "component_id",
        "name",
        "role",
        "accession",
        "source",
        "length_bp",
    }
)


class FormalReportSnapshotError(ValueError):
    """Raised when a supplied fact is not safe for a report snapshot."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, fallback: str = "") -> str:
    value = " ".join(str(value or "").replace("\x00", "").split())
    return value or fallback


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _snapshot_id(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("ascii")).hexdigest()


_FORBIDDEN_KEY_PARTS = frozenset(
    {
        "fasta",
        "genbank",
        "primer",
        "payload",
        "session",
        "database",
        "repository",
        "raw",
    }
)
_SAFE_SEQUENCE_KEYS = frozenset(
    {
        "sequence_length",
        "sequence_sha256",
        "sequence_checksum",
        "canonical_hash",
        "canonical_sha256",
        "canonical_length",
        "canonical_length_bp",
        "dna_length",
        "dna_sha256",
    }
)
_TRUSTED_HASH_PATHS = frozenset(
    {
        ("construct_summary", "cassette_sha256"),
        ("construct_summary", "canonical_hash"),
        ("delivery_artifacts", "[]", "sha256"),
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_NUCLEOTIDE_RE = re.compile(r"^[ACGTUNRYKMSWBDHV]+$", re.IGNORECASE)
_SAFE_FACT_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SEQUENCE_MINIMUM_LENGTH = 8


def _normal_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _safe_key(key: str) -> str:
    normalized = _normal_key(key)
    if not normalized:
        raise FormalReportSnapshotError("Snapshot fact keys must be non-empty strings.")
    if not _SAFE_FACT_KEY_RE.fullmatch(key):
        raise FormalReportSnapshotError(f"Snapshot fact key '{key}' is not a stable scalar reference key.")
    if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
        raise FormalReportSnapshotError(f"Snapshot cannot retain '{key}' payload data.")
    if ("sequence" in normalized or "dna" in normalized) and normalized not in _SAFE_SEQUENCE_KEYS:
        raise FormalReportSnapshotError(f"Snapshot cannot retain raw sequence field '{key}'.")
    if normalized in {"data", "content", "bytes", "text"}:
        raise FormalReportSnapshotError(f"Snapshot cannot retain arbitrary '{key}' content.")
    return str(key)


def _is_trusted_hash_path(path: tuple[str, ...]) -> bool:
    """Only established snapshot fields may retain a nucleotide-looking digest."""
    return path in _TRUSTED_HASH_PATHS


def _looks_like_sequence(value: str) -> bool:
    return len(value) >= _SEQUENCE_MINIMUM_LENGTH and bool(_NUCLEOTIDE_RE.fullmatch(value))


def _normalized_sequence_candidate(value: str) -> str:
    """Normalize common display wrappers before checking for nucleotide content."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"^\s*5\s*['\u2018\u2019\u2032]\s*[-:]?\s*", "", normalized)
    normalized = re.sub(r"\s*[-:]?\s*3\s*['\u2018\u2019\u2032]\s*$", "", normalized)
    return re.sub(r"[\s\-_'\u2018\u2019\u2032.,;:/\\|()[\]{}<>]+", "", normalized)


def _clean_fact(value: Any, *, path: tuple[str, ...] = ()) -> Any:
    display_path = "snapshot" + "".join(f".{segment}" if segment != "[]" else "[]" for segment in path)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FormalReportSnapshotError(f"{display_path} must not contain non-finite numbers.")
        return value
    if isinstance(value, bytes):
        raise FormalReportSnapshotError(f"{display_path} must not contain bytes.")
    if isinstance(value, str):
        compact = value.strip()
        if compact.startswith(">") or re.search(r"(?im)^\s*(?:LOCUS|ORIGIN)\b", compact):
            raise FormalReportSnapshotError(f"{display_path} appears to contain an export payload.")
        if _is_trusted_hash_path(path) and compact and not _SHA256_RE.fullmatch(compact):
            raise FormalReportSnapshotError(f"{display_path} must contain a 64-character hexadecimal SHA-256 value.")
        # Hash fields retain valid SHA-256 values for local traceability.  They
        # are not provider inputs, so a valid A/C/G/T-only digest is not DNA.
        is_valid_hash = _is_trusted_hash_path(path) and bool(_SHA256_RE.fullmatch(compact))
        if not is_valid_hash and _looks_like_sequence(_normalized_sequence_candidate(compact)):
            raise FormalReportSnapshotError(f"{display_path} appears to contain raw DNA.")
        return _text(value)
    if isinstance(value, Mapping):
        return {
            _safe_key(str(key)): _clean_fact(item, path=path + (str(key),))
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence):
        return [_clean_fact(item, path=path + ("[]",)) for item in value]
    raise FormalReportSnapshotError(f"{display_path} has unsupported value type {type(value).__name__}.")


def _artifact_inventory(exports: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Derive metadata from existing payloads without retaining those payloads."""
    artifacts: list[dict[str, Any]] = []
    for export_name, raw_record in sorted(exports.items(), key=lambda item: str(item[0])):
        record = _mapping(raw_record)
        raw = record.get("data")
        if isinstance(raw, str):
            payload = raw.encode("utf-8")
        elif isinstance(raw, bytes):
            payload = raw
        else:
            payload = b""
        digest = _text(record.get("sha256") or record.get("checksum"))
        if not digest and payload:
            digest = hashlib.sha256(payload).hexdigest()
        artifacts.append(
            {
                "artifact_id": _text(export_name),
                "file_name": _text(record.get("file_name"), f"{export_name}.txt"),
                "available": bool(payload),
                "size_bytes": len(payload),
                "sha256": digest,
            }
        )
    return artifacts


def _component_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for index, raw in enumerate(value if isinstance(value, Sequence) and not isinstance(value, str) else []):
        item = _mapping(raw)
        refs.append(
            {
                "order": index + 1,
                "component_id": _text(item.get("id") or item.get("component_id")),
                "name": _text(item.get("name") or item.get("display_name") or item.get("label")),
                "role": _text(item.get("role") or item.get("type") or item.get("biological_role")),
                "accession": _text(item.get("accession") or item.get("source_accession")),
                "source": _text(item.get("source") or item.get("source_type")),
                "length_bp": int(item.get("length_bp") or item.get("sequence_length") or 0),
            }
        )
    return refs


def _feature_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for index, raw in enumerate(value if isinstance(value, Sequence) and not isinstance(value, str) else []):
        item = _mapping(raw)
        refs.append(
            {
                "order": index + 1,
                "feature_id": _text(item.get("id") or item.get("feature_id")),
                "name": _text(item.get("name") or item.get("label")),
                "role": _text(item.get("role") or item.get("type")),
                "start": int(item.get("start") or item.get("start_1based") or 0),
                "end": int(item.get("end") or item.get("end_1based") or 0),
                "strand": int(item.get("strand") or 0),
                "accession": _text(item.get("accession") or item.get("source_accession")),
            }
        )
    return refs


def _validate_multi_tu_registry_report_inputs(
    data: Mapping[str, Any], *, registry_path: str | Path | None = None
) -> None:
    original_input = _mapping(data.get("original_input"))
    units = original_input.get("expression_units")
    if not isinstance(units, list):
        return
    from services.plant_component_workflow_registry import (
        REGISTRY_SOURCE_TYPE,
        PlantComponentRegistryError,
        admit_registry_selection,
        validate_saved_selection,
    )

    for raw_unit in units:
        unit = _mapping(raw_unit)
        for role in (
            "promoter",
            "five_prime_region",
            "cds",
            "3_prime_regulatory_region",
        ):
            component_input = _mapping(unit.get(role))
            reference = _mapping(component_input.get("component_reference"))
            if not reference:
                continue
            sequence = _text(reference.get("selected_sequence"))
            try:
                validated = validate_saved_selection(
                    reference, role=role, sequence=sequence
                )
                if _text(validated.get("source_type")) == REGISTRY_SOURCE_TYPE:
                    admit_registry_selection(
                        validated,
                        role=role,
                        sequence=sequence,
                        workflow_id=_text(validated.get("workflow_context"))
                        or "generic_multi_tu",
                        path=registry_path,
                    )
            except PlantComponentRegistryError as exc:
                raise FormalReportSnapshotError(
                    f"Registry selection blocks the formal report snapshot: {exc}"
                ) from exc


def build_formal_report_snapshot(
    *,
    workflow_type: str,
    freshness: Mapping[str, Any] | None = None,
    project: Mapping[str, Any] | None = None,
    host: Mapping[str, Any] | None = None,
    design_goal: Mapping[str, Any] | None = None,
    biological_inputs: Mapping[str, Any] | None = None,
    component_summary: Mapping[str, Any] | None = None,
    construct_summary: Mapping[str, Any] | None = None,
    feature_summary: Mapping[str, Any] | None = None,
    validation_summary: Mapping[str, Any] | None = None,
    provenance_summary: Mapping[str, Any] | None = None,
    delivery_artifacts: Sequence[Mapping[str, Any]] | None = None,
    route_specific_data: Mapping[str, Any] | None = None,
    boundary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one JSON-compatible snapshot with a stable content hash identity."""
    if workflow_type not in WORKFLOW_TYPES:
        raise FormalReportSnapshotError(f"Unsupported workflow type: {workflow_type!r}.")
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "workflow_type": workflow_type,
        "freshness": _clean_fact(_mapping(freshness), path=("freshness",)),
        "project": _clean_fact(_mapping(project), path=("project",)),
        "host": _clean_fact(_mapping(host), path=("host",)),
        "design_goal": _clean_fact(_mapping(design_goal), path=("design_goal",)),
        "biological_inputs": _clean_fact(_mapping(biological_inputs), path=("biological_inputs",)),
        "component_summary": _clean_fact({"components": [], **_mapping(component_summary)}, path=("component_summary",)),
        "construct_summary": _clean_fact(_mapping(construct_summary), path=("construct_summary",)),
        "feature_summary": _clean_fact(_mapping(feature_summary), path=("feature_summary",)),
        "validation_summary": _clean_fact(_mapping(validation_summary), path=("validation_summary",)),
        "provenance_summary": _clean_fact(_mapping(provenance_summary), path=("provenance_summary",)),
        "delivery_artifacts": _clean_fact(list(delivery_artifacts or []), path=("delivery_artifacts",)),
        "route_specific_data": _clean_fact(_mapping(route_specific_data), path=("route_specific_data",)),
        "boundary": _clean_fact(
            _mapping(boundary)
            or {
                "documentation_only": True,
                "manual_review_required": True,
                "does_not_establish": [
                    "experimental validation",
                    "wet-lab readiness",
                    "expression outcome",
                ],
            },
            path=("boundary",),
        ),
    }
    snapshot = {"snapshot_id": _snapshot_id(payload), **payload}
    return validate_formal_report_snapshot(snapshot)


def validate_formal_report_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return an isolated copy of a FormalReportSnapshot."""
    data = _mapping(snapshot)
    # Snapshot identity is an integrity boundary.  It deliberately precedes
    # schema/type validation so malformed, stale content cannot choose a later
    # schema error over an ID/content mismatch.
    supplied_id = data.get("snapshot_id")
    if not isinstance(supplied_id, str) or not _SHA256_RE.fullmatch(supplied_id):
        raise FormalReportSnapshotError("Snapshot ID must be a 64-character hexadecimal SHA-256 value.")
    payload = {key: value for key, value in data.items() if key != "snapshot_id"}
    try:
        expected_id = _snapshot_id(payload)
    except (TypeError, ValueError) as exc:
        raise FormalReportSnapshotError("Snapshot contents cannot form a deterministic integrity identity.") from exc
    if supplied_id != expected_id:
        raise FormalReportSnapshotError("Snapshot ID does not match deterministic contents.")
    required = {
        "schema_version", "snapshot_id", "workflow_type", "freshness", "project", "host",
        "design_goal", "biological_inputs", "component_summary", "construct_summary",
        "feature_summary", "validation_summary", "provenance_summary", "delivery_artifacts",
        "route_specific_data", "boundary",
    }
    if set(data) != required:
        missing, extra = required - set(data), set(data) - required
        raise FormalReportSnapshotError(f"Snapshot schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}.")
    # Do not coerce a received snapshot at this trust boundary.  Projection
    # builders rely on these containers, so coercion would turn malformed
    # caller input into a later AttributeError/TypeError instead of a stable
    # rejected result.
    mapping_fields = {
        "freshness", "project", "host", "design_goal", "biological_inputs",
        "component_summary", "construct_summary", "feature_summary",
        "validation_summary", "provenance_summary", "route_specific_data", "boundary",
    }
    for field in mapping_fields:
        if not isinstance(data[field], Mapping):
            raise FormalReportSnapshotError(f"Snapshot field '{field}' must be a mapping.")
    if not isinstance(data["delivery_artifacts"], list):
        raise FormalReportSnapshotError("Snapshot field 'delivery_artifacts' must be a list.")
    if not isinstance(data["component_summary"].get("components"), list):
        raise FormalReportSnapshotError("Snapshot field 'component_summary.components' must be a list.")
    for index, component in enumerate(data["component_summary"]["components"]):
        if not isinstance(component, Mapping):
            raise FormalReportSnapshotError(f"Snapshot component_summary.components[{index}] must be a mapping.")
        if set(component) != _COMPONENT_RECORD_FIELDS:
            raise FormalReportSnapshotError(
                f"Snapshot component_summary.components[{index}] must use the exact component-record schema."
            )
        if (
            not isinstance(component["order"], int)
            or isinstance(component["order"], bool)
            or component["order"] < 1
            or not isinstance(component["length_bp"], int)
            or isinstance(component["length_bp"], bool)
            or component["length_bp"] < 0
            or any(not isinstance(component[field], str) for field in _COMPONENT_RECORD_FIELDS - {"order", "length_bp"})
        ):
            raise FormalReportSnapshotError(
                f"Snapshot component_summary.components[{index}] has invalid typed component-record values."
            )
    for index, artifact in enumerate(data["delivery_artifacts"]):
        if not isinstance(artifact, Mapping):
            raise FormalReportSnapshotError(f"Snapshot delivery_artifacts[{index}] must be a mapping.")
    if not isinstance(data["schema_version"], str) or not isinstance(data["workflow_type"], str):
        raise FormalReportSnapshotError("Snapshot schema and workflow identifiers must be strings.")
    cleaned = _clean_fact(payload)
    if cleaned.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise FormalReportSnapshotError("Unsupported snapshot schema version.")
    if cleaned.get("workflow_type") not in WORKFLOW_TYPES:
        raise FormalReportSnapshotError("Unsupported snapshot workflow type.")
    return copy.deepcopy({"snapshot_id": expected_id, **cleaned})


def build_single_gene_snapshot(
    *,
    result: Mapping[str, Any],
    cassette: Mapping[str, Any],
    plasmid: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
    project: Mapping[str, Any] | None = None,
    host: Mapping[str, Any] | None = None,
    design_goal: Mapping[str, Any] | None = None,
    biological_inputs: Mapping[str, Any] | None = None,
    provenance_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt explicit formal single-gene result facts without reading runtime state."""
    result_data, cassette_data, plasmid_data = _mapping(result), _mapping(cassette), _mapping(plasmid)
    supplied_project = {"project_id": result_data.get("project_id"), "name": result_data.get("project_name"), **_mapping(project)}
    validation = _mapping(plasmid_data.get("validation_summary"))
    return build_formal_report_snapshot(
        workflow_type="single_gene",
        freshness=freshness or {"state": "current" if result_data.get("input_signature") else "unknown", "input_signature": result_data.get("input_signature")},
        project=supplied_project,
        host=host,
        design_goal=design_goal,
        biological_inputs=biological_inputs,
        component_summary={"components": _component_refs(cassette_data.get("components"))},
        construct_summary={
            "canonical_construct_present": bool(plasmid_data),
            "cassette_length_bp": int(cassette_data.get("sequence_length") or 0),
            "cassette_sha256": cassette_data.get("sequence_checksum"),
            "canonical_length_bp": int(plasmid_data.get("sequence_length") or 0),
            "canonical_hash": plasmid_data.get("sequence_checksum"),
            "topology": plasmid_data.get("topology"),
        },
        feature_summary={"features": _feature_refs(plasmid_data.get("features") or plasmid_data.get("feature_coordinates"))},
        validation_summary={
            "blocking_count": int(validation.get("blocking_count") or 0),
            "warning_count": int(validation.get("warning_count") or 0),
            "info_count": int(validation.get("info_count") or 0),
        },
        provenance_summary=provenance_summary,
        delivery_artifacts=_artifact_inventory(_mapping(result_data.get("exports"))),
        route_specific_data={"route": "single_gene", "canonical_status": plasmid_data.get("construct_status")},
    )


def build_multi_tu_snapshot(
    *,
    multi_tu_result: Mapping[str, Any],
    freshness: Mapping[str, Any] | None = None,
    project: Mapping[str, Any] | None = None,
    host: Mapping[str, Any] | None = None,
    design_goal: Mapping[str, Any] | None = None,
    biological_inputs: Mapping[str, Any] | None = None,
    provenance_summary: Mapping[str, Any] | None = None,
    registry_path: str | Path | None = None,
) -> dict[str, Any]:
    """Adapt explicit ordered multi-TU facts supplied by the caller."""
    data = _mapping(multi_tu_result)
    _validate_multi_tu_registry_report_inputs(data, registry_path=registry_path)
    units = data.get("transcription_units") or data.get("units") or data.get("ordered_tus") or []
    normalized_units = []
    for index, raw_unit in enumerate(units if isinstance(units, Sequence) and not isinstance(units, str) else []):
        unit = _mapping(raw_unit)
        normalized_units.append(
            {
                "order": index + 1,
                "tu_id": _text(unit.get("tu_id") or unit.get("id")),
                "orientation": _text(unit.get("orientation") or unit.get("strand")),
                "length_bp": int(unit.get("length_bp") or unit.get("sequence_length") or 0),
                "component_refs": _component_refs(unit.get("components") or unit.get("component_refs")),
                "ranges": _feature_refs(unit.get("ranges") or unit.get("features")),
            }
        )
    validation = _mapping(data.get("validation_summary"))
    canonical = _mapping(data.get("canonical_construct") or data.get("complete_plasmid"))
    return build_formal_report_snapshot(
        workflow_type="multi_tu",
        freshness=freshness or _mapping(data.get("freshness")),
        project=project or _mapping(data.get("project")),
        host=host,
        design_goal=design_goal,
        biological_inputs=biological_inputs,
        component_summary={
            "transcription_unit_count": len(normalized_units),
            "components": [
                component
                for unit in normalized_units
                for component in unit["component_refs"]
            ],
        },
        construct_summary={
            "canonical_construct_present": bool(canonical),
            "canonical_length_bp": int(canonical.get("sequence_length") or canonical.get("total_length") or 0),
            "canonical_hash": canonical.get("sequence_checksum") or canonical.get("sequence_sha256"),
            "topology": canonical.get("topology"),
        },
        feature_summary={"features": _feature_refs(canonical.get("features") or data.get("features"))},
        validation_summary={"blocking_count": int(validation.get("blocking_count") or 0), "warning_count": int(validation.get("warning_count") or 0)},
        provenance_summary=provenance_summary,
        delivery_artifacts=_artifact_inventory(_mapping(data.get("exports"))),
        route_specific_data={"route": "multi_tu", "ordered_transcription_units": normalized_units},
    )


def build_pathway_snapshot(
    *,
    pathway_facts: Mapping[str, Any],
    canonical_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt caller-provided pathway facts; missing canonical output stays explicit."""
    facts, canonical = _mapping(pathway_facts), _mapping(canonical_result)
    validation = _mapping(facts.get("validation_summary"))
    return build_formal_report_snapshot(
        workflow_type="pathway",
        freshness=_mapping(facts.get("freshness")),
        project=_mapping(facts.get("project")),
        host=_mapping(facts.get("host")),
        design_goal=_mapping(facts.get("design_goal")),
        biological_inputs=_mapping(facts.get("biological_inputs")),
        component_summary=_mapping(facts.get("component_summary")),
        construct_summary={
            "canonical_construct_present": bool(canonical),
            "canonical_length_bp": int(canonical.get("sequence_length") or canonical.get("total_length") or 0),
            "canonical_hash": canonical.get("sequence_checksum") or canonical.get("sequence_sha256"),
            "topology": canonical.get("topology"),
        },
        feature_summary=_mapping(facts.get("feature_summary")),
        validation_summary={"blocking_count": int(validation.get("blocking_count") or 0), "warning_count": int(validation.get("warning_count") or 0)},
        provenance_summary=_mapping(facts.get("provenance_summary")),
        delivery_artifacts=_artifact_inventory(_mapping(facts.get("exports"))),
        route_specific_data={"route": "pathway", "pathway_facts": _mapping(facts.get("route_specific_data"))},
    )
