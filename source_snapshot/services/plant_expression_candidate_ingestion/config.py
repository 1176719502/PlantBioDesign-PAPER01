from __future__ import annotations

import os
from pathlib import Path


SCHEMA_VERSION = "v2.7-r225-plant-expression-candidate-db"
MANIFEST_SCHEMA_VERSION = "v2.7-r225-ingestion-run-manifest"
QUERY_PLAN_SCHEMA_VERSION = "v2.7-r225-query-plan"
SOURCE_REGISTRY_SCHEMA_VERSION = "v2.7-r225-source-registry"
DEFAULT_QUERY_PLAN_ID = "plant_expression_batch_1"
PLANT_EXPRESSION_KNOWLEDGE_ENV = "BIODESIGN_PLANT_EXPRESSION_KB_DIR"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_REGISTRY_PATH = REPO_ROOT / "data" / "plant_expression_ingestion" / "source_registry.v1.json"
DEFAULT_QUERY_PLAN_PATH = (
    REPO_ROOT
    / "data"
    / "plant_expression_ingestion"
    / "plant_expression_batch_1.query_plan.json"
)

REVIEW_STATUS_VALUES = {"candidate", "unreviewed", "needs_manual_review"}
PROVENANCE_STATUS_VALUES = {"candidate", "source_metadata_preserved"}
EVIDENCE_STATUS_VALUES = {"metadata_candidate", "accession_metadata_candidate"}
RECORD_TYPES = {
    "publication",
    "sequence_or_accession",
    "component_candidate",
    "vector_or_toolkit_candidate",
    "evidence_candidate",
}


def default_data_root() -> Path:
    override = os.environ.get(PLANT_EXPRESSION_KNOWLEDGE_ENV)
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / "BioDesignStudio" / "plant_expression_knowledge"
    return Path.home() / ".biodesign_studio" / "plant_expression_knowledge"
