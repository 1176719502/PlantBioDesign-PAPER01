from __future__ import annotations

from pathlib import Path


APPLICATION_ID = 1_262_634_032
SCHEMA_VERSION = 1
IMPORT_SCHEMA_VERSION = "kb00-import-v0"
CONTRACT_VERSION = "KB00-1.0-draft"
QUERY_CONTRACT_VERSION = "KnowledgeQueryV0"
BUILD_TOOL_VERSION = "kb00-builder-v1"
WRITER_CONTRACT_VERSION = "KB00-pinned-sqlite-writer-v1"
REQUIRED_SQLITE_VERSION = (3, 49, 1)
REQUIRED_SQLITE_SOURCE_ID = (
    "2025-02-18 13:38:58 "
    "873d4e274b4988d260ba8354a9718324a1c26187a4ab4c1cc0227c03d0f10e70"
)
REQUIRED_SQLITE_COMPILE_OPTIONS_SHA256 = (
    "b281a2c57cd63a06a45d7c27170b39fed08fbbde4fa35dc7e701a4d23b346bc1"
)

RESOURCE_DIRECTORY = Path("data") / "knowledge_base_v0"
DATABASE_FILENAME = "kb_v0.sqlite3"
MANIFEST_FILENAME = "manifest.json"
BUILD_PROVENANCE_FILENAME = "build_provenance.json"
DATABASE_RELATIVE_PATH = (RESOURCE_DIRECTORY / DATABASE_FILENAME).as_posix()
MANIFEST_RELATIVE_PATH = (RESOURCE_DIRECTORY / MANIFEST_FILENAME).as_posix()
BUILD_PROVENANCE_RELATIVE_PATH = (RESOURCE_DIRECTORY / BUILD_PROVENANCE_FILENAME).as_posix()

ENTITY_TYPES = (
    "paper",
    "source_reference",
    "organism",
    "tissue",
    "experiment",
    "design_case",
    "construct",
    "transcription_unit",
    "component",
    "component_evidence",
    "metabolite",
    "measurement",
    "accession",
    "evidence_claim",
    "evidence_level",
    "applicability_scope",
    "limitation",
)

FACT_CLASSES = ("FACT", "DERIVATION", "INFERENCE", "UNKNOWN")
CONTEXT_STATES = ("KNOWN", "UNKNOWN", "NOT_APPLICABLE")
LIFECYCLE_STATES = ("ACTIVE", "SUPERSEDED", "RETIRED", "WITHDRAWN")
ACTOR_TYPES = ("HUMAN", "IMPORT", "AI")
REVIEW_STATES = (
    "UNREVIEWED",
    "PENDING_HUMAN_REVIEW",
    "HUMAN_APPROVED",
    "HUMAN_REJECTED",
    "SUPERSEDED",
    "RETIRED",
)

SNAPSHOT_FIELD = "kb_reference_snapshot_v0"
SNAPSHOT_REQUIRED_FIELDS = (
    "kb_contract_version",
    "kb_dataset_version",
    "entity_key",
    "entity_revision",
    "entity_payload_sha256",
    "selected_sequence_sha256",
    "snapshot_created_at_utc",
)
