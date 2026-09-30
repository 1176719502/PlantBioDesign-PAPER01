from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.plant_expression_candidate_ingestion.utils import content_hash, ensure_safe_id, write_json


@dataclass(frozen=True)
class KnowledgePaths:
    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def normalized_dir(self) -> Path:
        return self.root / "normalized"

    @property
    def database_dir(self) -> Path:
        return self.root / "database"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "manifests"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def database_path(self) -> Path:
        return self.database_dir / "plant_expression_candidates.sqlite3"

    def ensure_runtime_dirs(self) -> None:
        for path in (self.raw_dir, self.normalized_dir, self.database_dir, self.manifests_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RawSnapshotResult:
    relative_path: str
    content_hash: str


class RawSnapshotStore:
    def __init__(self, paths: KnowledgePaths):
        self.paths = paths

    def write_snapshot(
        self,
        *,
        source_id: str,
        ingestion_run_id: str,
        query_id: str,
        page_index: int,
        payload: dict[str, Any],
    ) -> RawSnapshotResult:
        clean_source = ensure_safe_id(source_id, "source_id")
        clean_run = ensure_safe_id(ingestion_run_id, "ingestion_run_id")
        clean_query = ensure_safe_id(query_id, "query_id")
        target = self.paths.raw_dir / clean_source / clean_run / f"{clean_query}.page-{page_index:05d}.json"
        if target.exists():
            raise FileExistsError(f"Raw snapshot already exists: {target}")
        snapshot_hash = content_hash(payload)
        write_json(target, payload)
        return RawSnapshotResult(
            relative_path=str(target.relative_to(self.paths.root)).replace("\\", "/"),
            content_hash=snapshot_hash,
        )
