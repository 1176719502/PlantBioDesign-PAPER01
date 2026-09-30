from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from services.plant_expression_candidate_ingestion.adapters import AdapterConfig, build_adapter
from services.plant_expression_candidate_ingestion.config import (
    DEFAULT_QUERY_PLAN_PATH,
    DEFAULT_SOURCE_REGISTRY_PATH,
    MANIFEST_SCHEMA_VERSION,
)
from services.plant_expression_candidate_ingestion.normalizers import normalize_records
from services.plant_expression_candidate_ingestion.registry import (
    QueryDefinition,
    SourceDefinition,
    load_query_plan,
    load_source_registry,
)
from services.plant_expression_candidate_ingestion.repository import CandidateRepository
from services.plant_expression_candidate_ingestion.storage import KnowledgePaths, RawSnapshotStore
from services.plant_expression_candidate_ingestion.utils import build_run_id, content_hash, utc_now, write_json


@dataclass(frozen=True)
class IngestionOptions:
    data_root: Path
    source_id: str
    query_plan_path: Path = DEFAULT_QUERY_PLAN_PATH
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY_PATH
    query_ids: tuple[str, ...] = ()
    max_records: int = 0
    page_size: int = 100
    timeout: float = 20.0
    retries: int = 2
    retry_delay: float = 1.0
    pace_seconds: float = 0.2
    dry_run: bool = False
    resume: bool = False
    explicit_run_id: str = ""


def preview_queries(options: IngestionOptions) -> dict[str, Any]:
    sources = load_source_registry(options.source_registry_path)
    query_plan = load_query_plan(options.query_plan_path)
    selected_sources = _select_sources(sources, options.source_id)
    selected_queries = _select_queries(query_plan["queries"], options.query_ids)
    return {
        "dry_run": True,
        "query_plan_id": query_plan["query_plan_id"],
        "sources": [source.source_id for source in selected_sources],
        "queries": [
            {
                "query_id": query.query_id,
                "domain_label": query.domain_label,
                "enabled": query.enabled,
                "max_records": query.max_records,
                "source_queries": {
                    source.source_id: query.query_for_source(source.source_id)
                    for source in selected_sources
                    if query.query_for_source(source.source_id)
                },
            }
            for query in selected_queries
        ],
    }


def run_ingestion(options: IngestionOptions) -> dict[str, Any]:
    if options.dry_run:
        return preview_queries(options)
    paths = KnowledgePaths(options.data_root)
    paths.ensure_runtime_dirs()
    sources = load_source_registry(options.source_registry_path)
    query_plan = load_query_plan(options.query_plan_path)
    selected_sources = _select_sources(sources, options.source_id)
    selected_queries = _select_queries(query_plan["queries"], options.query_ids)
    repo = CandidateRepository(paths.database_path)
    schema_info = repo.init_schema()
    snapshot_store = RawSnapshotStore(paths)
    overall = {
        "query_plan_id": query_plan["query_plan_id"],
        "data_root": str(paths.root),
        "database_path": str(paths.database_path),
        "schema_info": schema_info,
        "runs": [],
        "retrieved_count": 0,
        "normalized_count": 0,
        "duplicate_count": 0,
        "rejected_count": 0,
        "error_count": 0,
        "inserted_count": 0,
        "elapsed_seconds": 0.0,
    }
    started_clock = monotonic()
    for source in selected_sources:
        run_summary = _run_source(
            source=source,
            query_plan_id=query_plan["query_plan_id"],
            queries=selected_queries,
            repo=repo,
            paths=paths,
            snapshot_store=snapshot_store,
            options=options,
        )
        overall["runs"].append(run_summary)
        for key in ("retrieved_count", "normalized_count", "duplicate_count", "rejected_count", "error_count", "inserted_count"):
            overall[key] += int(run_summary.get(key, 0))
    overall["elapsed_seconds"] = round(monotonic() - started_clock, 3)
    overall["database_stats"] = repo.stats()
    return overall


def _run_source(
    *,
    source: SourceDefinition,
    query_plan_id: str,
    queries: list[QueryDefinition],
    repo: CandidateRepository,
    paths: KnowledgePaths,
    snapshot_store: RawSnapshotStore,
    options: IngestionOptions,
) -> dict[str, Any]:
    started_at = utc_now()
    run_id = build_run_id(source.source_id, started_at, options.explicit_run_id or None)
    repo.register_source(source)
    repo.start_run(
        {
            "ingestion_run_id": run_id,
            "source_id": source.source_id,
            "query_plan_id": query_plan_id,
            "adapter_version": source.adapter_version,
            "started_at": started_at,
            "software_git_commit": _git_commit(),
        }
    )
    adapter = build_adapter(
        source,
        config=AdapterConfig(
            timeout=options.timeout,
            retries=options.retries,
            retry_delay=options.retry_delay,
            page_size=options.page_size,
            pace_seconds=options.pace_seconds,
        ),
    )
    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "ingestion_run_id": run_id,
        "source_id": source.source_id,
        "source_name": source.source_name,
        "adapter_version": source.adapter_version,
        "query_plan_id": query_plan_id,
        "started_at": started_at,
        "finished_at": "",
        "completion_status": "running",
        "retrieved_count": 0,
        "normalized_count": 0,
        "duplicate_count": 0,
        "rejected_count": 0,
        "error_count": 0,
        "inserted_count": 0,
        "source_url_or_endpoint": source.base_url,
        "source_data_version": "",
        "license_or_usage_policy_note": f"{source.license_note} {source.usage_policy_note}".strip(),
        "software_git_commit": _git_commit(),
        "queries": [],
        "snapshot_hashes": [],
    }
    try:
        remaining_budget = options.max_records
        for query in queries:
            query_params = query.query_for_source(source.source_id)
            if not query.enabled or not query_params:
                continue
            per_query_max = query.max_records
            if remaining_budget:
                per_query_max = min(per_query_max, max(remaining_budget, 0))
            if per_query_max <= 0:
                break
            repo.register_query(query_plan_id, source.source_id, query, query_params)
            pages = adapter.fetch_pages(query_params, max_records=per_query_max)
            query_summary = {
                "query_id": query.query_id,
                "description": query.description,
                "request_parameters": query_params,
                "retrieved_count": 0,
                "normalized_count": 0,
                "duplicate_count": 0,
                "rejected_count": 0,
                "error_count": 0,
                "raw_snapshots": [],
            }
            for page_index, page in enumerate(pages, start=1):
                snapshot_payload = {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "ingestion_run_id": run_id,
                    "source_id": source.source_id,
                    "query_id": query.query_id,
                    "endpoint": page.endpoint,
                    "request_parameters": page.request_params,
                    "fetched_at": utc_now(),
                    "payload": page.payload,
                }
                snapshot = snapshot_store.write_snapshot(
                    source_id=source.source_id,
                    ingestion_run_id=run_id,
                    query_id=query.query_id,
                    page_index=page_index,
                    payload=snapshot_payload,
                )
                normalized, rejected = normalize_records(source=source, query=query, records=page.records)
                insert_stats = repo.insert_records(
                    ingestion_run_id=run_id,
                    query_id=query.query_id,
                    raw_snapshot_path=snapshot.relative_path,
                    raw_snapshot_hash=snapshot.content_hash,
                    records=normalized,
                )
                retrieved = len(page.records)
                query_summary["retrieved_count"] += retrieved
                query_summary["normalized_count"] += len(normalized)
                query_summary["rejected_count"] += len(rejected)
                query_summary["duplicate_count"] += insert_stats["duplicate_count"]
                query_summary["raw_snapshots"].append(
                    {
                        "path": snapshot.relative_path,
                        "content_hash": snapshot.content_hash,
                        "record_count": retrieved,
                    }
                )
                summary["snapshot_hashes"].append(snapshot.content_hash)
                summary["inserted_count"] += insert_stats["inserted_count"]
                if remaining_budget:
                    remaining_budget -= retrieved
            summary["queries"].append(query_summary)
            for key in ("retrieved_count", "normalized_count", "duplicate_count", "rejected_count", "error_count"):
                summary[key] += int(query_summary.get(key, 0))
        summary["completion_status"] = "completed"
    except Exception as exc:
        summary["completion_status"] = "failed"
        summary["error_count"] += 1
        summary["fatal_error"] = str(exc)
    summary["finished_at"] = utc_now()
    summary["manifest_hash"] = content_hash(summary)
    manifest_path = paths.manifests_dir / f"{run_id}.manifest.json"
    write_json(manifest_path, summary)
    manifest_rel = str(manifest_path.relative_to(paths.root)).replace("\\", "/")
    repo.finish_run(run_id, status=summary["completion_status"], manifest_path=manifest_rel, summary=summary)
    return summary | {"manifest_path": manifest_rel}


def _select_sources(sources: dict[str, SourceDefinition], source_id: str) -> list[SourceDefinition]:
    if source_id == "all":
        return [source for source in sources.values() if source.enabled]
    if source_id not in sources:
        raise ValueError(f"Unknown source: {source_id}")
    source = sources[source_id]
    if not source.enabled:
        raise ValueError(f"Source is disabled: {source_id}")
    return [source]


def _select_queries(queries: list[QueryDefinition], query_ids: tuple[str, ...]) -> list[QueryDefinition]:
    if not query_ids:
        return [query for query in queries if query.enabled]
    wanted = set(query_ids)
    selected = [query for query in queries if query.query_id in wanted]
    missing = wanted - {query.query_id for query in selected}
    if missing:
        raise ValueError(f"Unknown query IDs: {', '.join(sorted(missing))}")
    return selected


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""
