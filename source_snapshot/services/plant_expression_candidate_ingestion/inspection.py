from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_expression_candidate_ingestion.config import default_data_root
from services.plant_expression_candidate_ingestion.repository import CandidateRepository
from services.plant_expression_candidate_ingestion.storage import KnowledgePaths


def inspect_candidate_knowledge_base(
    *,
    data_root: str | Path | None = None,
    search: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    root = Path(data_root) if data_root is not None else default_data_root()
    paths = KnowledgePaths(root)
    repo = CandidateRepository(paths.database_path)
    stats = repo.stats(read_only=True)
    if search:
        stats["search"] = {"term": search, "results": repo.search(search, limit=limit, read_only=True)}
    return stats
