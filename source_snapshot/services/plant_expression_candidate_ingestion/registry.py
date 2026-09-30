from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.plant_expression_candidate_ingestion.config import (
    QUERY_PLAN_SCHEMA_VERSION,
    SOURCE_REGISTRY_SCHEMA_VERSION,
)
from services.plant_expression_candidate_ingestion.utils import clean_text, read_json


class RegistryError(ValueError):
    """Raised when a source registry or query plan is invalid."""


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    source_name: str
    adapter: str
    base_url: str
    endpoint_note: str
    license_note: str
    usage_policy_note: str
    enabled: bool = True
    adapter_version: str = "r225.v1"


@dataclass(frozen=True)
class QueryDefinition:
    query_id: str
    description: str
    domain_label: str
    enabled: bool
    max_records: int
    version_date: str
    notes: str
    source_queries: dict[str, dict[str, Any]]

    def query_for_source(self, source_id: str) -> dict[str, Any] | None:
        payload = self.source_queries.get(source_id)
        return dict(payload) if isinstance(payload, dict) else None


def load_source_registry(path: str | Path) -> dict[str, SourceDefinition]:
    payload = read_json(path)
    if payload.get("schema_version") != SOURCE_REGISTRY_SCHEMA_VERSION:
        raise RegistryError("Unsupported source registry schema_version.")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise RegistryError("Source registry must include at least one source.")
    resolved: dict[str, SourceDefinition] = {}
    for row in sources:
        if not isinstance(row, dict):
            raise RegistryError("Source definition must be an object.")
        source_id = clean_text(row.get("source_id"))
        source_name = clean_text(row.get("source_name"))
        adapter = clean_text(row.get("adapter"))
        base_url = clean_text(row.get("base_url"))
        if not source_id or not source_name or not adapter or not base_url:
            raise RegistryError("Source definition is missing required identity fields.")
        resolved[source_id] = SourceDefinition(
            source_id=source_id,
            source_name=source_name,
            adapter=adapter,
            base_url=base_url,
            endpoint_note=clean_text(row.get("endpoint_note")),
            license_note=clean_text(row.get("license_note")),
            usage_policy_note=clean_text(row.get("usage_policy_note")),
            enabled=bool(row.get("enabled", True)),
            adapter_version=clean_text(row.get("adapter_version")) or "r225.v1",
        )
    return resolved


def load_query_plan(path: str | Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload.get("schema_version") != QUERY_PLAN_SCHEMA_VERSION:
        raise RegistryError("Unsupported query plan schema_version.")
    plan_id = clean_text(payload.get("query_plan_id"))
    if not plan_id:
        raise RegistryError("Query plan is missing query_plan_id.")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise RegistryError("Query plan must include at least one query.")
    resolved_queries: list[QueryDefinition] = []
    seen_ids: set[str] = set()
    for row in queries:
        if not isinstance(row, dict):
            raise RegistryError("Query definition must be an object.")
        query_id = clean_text(row.get("query_id"))
        if not query_id or query_id in seen_ids:
            raise RegistryError("Query IDs must be non-empty and unique.")
        source_queries = row.get("source_queries")
        if not isinstance(source_queries, dict) or not source_queries:
            raise RegistryError(f"Query {query_id} must include source_queries.")
        try:
            max_records = int(row.get("max_records"))
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"Query {query_id} has invalid max_records.") from exc
        if max_records <= 0:
            raise RegistryError(f"Query {query_id} max_records must be positive.")
        seen_ids.add(query_id)
        resolved_queries.append(
            QueryDefinition(
                query_id=query_id,
                description=clean_text(row.get("description")),
                domain_label=clean_text(row.get("domain_label")),
                enabled=bool(row.get("enabled", True)),
                max_records=max_records,
                version_date=clean_text(row.get("date_version")),
                notes=clean_text(row.get("notes")),
                source_queries={key: dict(value) for key, value in source_queries.items() if isinstance(value, dict)},
            )
        )
    return {
        "query_plan_id": plan_id,
        "schema_version": payload["schema_version"],
        "description": clean_text(payload.get("description")),
        "queries": resolved_queries,
        "license_policy_note": clean_text(payload.get("license_policy_note")),
        "limitations": clean_text(payload.get("limitations")),
    }
