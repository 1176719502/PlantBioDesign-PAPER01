from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "plant_host_registry_v1" / "hosts.json"
REGISTRY_VERSION = "plant-host-registry-v1"
SINGLE_GENE_COMPLETE_VECTOR = "SINGLE_GENE_COMPLETE_VECTOR"
GENERIC_MULTI_TU_ASSEMBLY = "GENERIC_MULTI_TU_ASSEMBLY"
_WORKFLOW_LEVELS = frozenset({SINGLE_GENE_COMPLETE_VECTOR, GENERIC_MULTI_TU_ASSEMBLY})
_REQUIRED_FIELDS = frozenset(
    {
        "host_id",
        "common_name",
        "scientific_name",
        "aliases",
        "plant_scope",
        "workflow_levels",
        "workflow_contracts",
        "evidence_refs",
        "status",
        "display_order",
    }
)


class PlantHostRegistryError(ValueError):
    """Raised when the packaged Plant-Only Host Registry V1 is invalid."""


def _require_text(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlantHostRegistryError(f"{context}.{field} must be a non-empty string.")
    return value.strip()


def _validate_record(raw: Any, index: int) -> dict[str, Any]:
    context = f"records[{index}]"
    if not isinstance(raw, Mapping):
        raise PlantHostRegistryError(f"{context} must be an object.")
    record = dict(raw)
    missing = _REQUIRED_FIELDS - record.keys()
    if missing:
        raise PlantHostRegistryError(f"{context} is missing fields: {sorted(missing)}.")
    host_id = _require_text(record["host_id"], "host_id", context)
    _require_text(record["common_name"], "common_name", context)
    _require_text(record["scientific_name"], "scientific_name", context)
    if record["plant_scope"] != "plant":
        raise PlantHostRegistryError(f"{context}.plant_scope must be 'plant'.")
    if not isinstance(record["aliases"], list) or any(not isinstance(item, str) or not item.strip() for item in record["aliases"]):
        raise PlantHostRegistryError(f"{context}.aliases must be a list of non-empty strings.")
    levels = record["workflow_levels"]
    if not isinstance(levels, list) or not levels or any(level not in _WORKFLOW_LEVELS for level in levels):
        raise PlantHostRegistryError(f"{context}.workflow_levels contains an unsupported level.")
    if len(set(levels)) != len(levels):
        raise PlantHostRegistryError(f"{context}.workflow_levels must be unique.")
    contracts = record["workflow_contracts"]
    if not isinstance(contracts, Mapping) or set(contracts) != set(levels):
        raise PlantHostRegistryError(f"{context}.workflow_contracts must match workflow_levels.")
    for level in levels:
        contract = contracts[level]
        if not isinstance(contract, Mapping) or not isinstance(contract.get("contains_vector"), bool):
            raise PlantHostRegistryError(f"{context}.workflow_contracts.{level} requires boolean contains_vector.")
        if level == GENERIC_MULTI_TU_ASSEMBLY and contract["contains_vector"] is not False:
            raise PlantHostRegistryError(f"{context}.generic multi-TU contract must contain contains_vector=false.")
    if not isinstance(record["evidence_refs"], list) or any(not isinstance(item, str) or not item.strip() for item in record["evidence_refs"]):
        raise PlantHostRegistryError(f"{context}.evidence_refs must be a list of non-empty strings.")
    _require_text(record["status"], "status", context)
    if isinstance(record["display_order"], bool) or not isinstance(record["display_order"], int) or record["display_order"] < 1:
        raise PlantHostRegistryError(f"{context}.display_order must be a positive integer.")
    return record


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    """Load and strictly validate the packaged, read-only host registry."""
    registry_path = Path(path) if path is not None else REGISTRY_PATH
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlantHostRegistryError("Plant Host Registry V1 cannot be read.") from exc
    if not isinstance(payload, Mapping) or set(payload) != {"registry_version", "records"}:
        raise PlantHostRegistryError("Plant Host Registry V1 has an invalid top-level schema.")
    if payload["registry_version"] != REGISTRY_VERSION or not isinstance(payload["records"], list):
        raise PlantHostRegistryError("Plant Host Registry V1 has an invalid version or records field.")
    records = [_validate_record(raw, index) for index, raw in enumerate(payload["records"])]
    if len({record["host_id"] for record in records}) != len(records):
        raise PlantHostRegistryError("Registry host_id values must be unique.")
    if len({record["display_order"] for record in records}) != len(records):
        raise PlantHostRegistryError("Registry display_order values must be unique.")
    records.sort(key=lambda record: record["display_order"])
    return {"registry_version": REGISTRY_VERSION, "records": copy.deepcopy(records)}


def list_hosts(path: str | Path | None = None) -> list[dict[str, Any]]:
    return copy.deepcopy(load_registry(path)["records"])


def hosts_for_workflow(workflow_level: str, path: str | Path | None = None) -> list[dict[str, Any]]:
    if workflow_level not in _WORKFLOW_LEVELS:
        raise PlantHostRegistryError(f"Unsupported workflow level: {workflow_level!r}.")
    return [record for record in list_hosts(path) if workflow_level in record["workflow_levels"]]


# Explicit aliases keep the public read API discoverable without adding state.
load_plant_host_registry = load_registry
get_hosts_for_workflow = hosts_for_workflow
