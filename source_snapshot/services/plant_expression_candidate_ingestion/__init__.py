"""Plant expression candidate ingestion foundation.

Modules in this package are intentionally side-effect free on import. Storage
directories and SQLite databases are created only by explicit runtime calls.
"""

from services.plant_expression_candidate_ingestion.config import (
    DEFAULT_QUERY_PLAN_ID,
    DEFAULT_SOURCE_REGISTRY_PATH,
    PLANT_EXPRESSION_KNOWLEDGE_ENV,
    default_data_root,
)

__all__ = [
    "DEFAULT_QUERY_PLAN_ID",
    "DEFAULT_SOURCE_REGISTRY_PATH",
    "PLANT_EXPRESSION_KNOWLEDGE_ENV",
    "default_data_root",
]
