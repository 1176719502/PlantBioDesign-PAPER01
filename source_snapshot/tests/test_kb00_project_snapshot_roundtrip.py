from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

from services.knowledge_base.reader import open_knowledge_base
from services.knowledge_base.snapshot import (
    KnowledgeReferenceSnapshot,
    attach_snapshot_to_project_payload,
    snapshot_from_project_payload,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
)
from services.plant_project_draft_schema import PlantDesignProjectDraft
from tests.kb00_helpers import build_synthetic_release


def _sqlite_project_repository(database_path: Path) -> SqlitePlantProjectDraftRepository:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            "CREATE TABLE project_history ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, project_name TEXT NOT NULL, "
            "version INTEGER NOT NULL, chassis TEXT NOT NULL, design_data TEXT NOT NULL, "
            "created_at TEXT NOT NULL, creator TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.commit()
    finally:
        connection.close()
    return SqlitePlantProjectDraftRepository(database_path)


def _project_payload_with_snapshot(tmp_path: Path) -> tuple[dict, dict]:
    release = build_synthetic_release(tmp_path / "release")
    with open_knowledge_base(release.database_path, release.manifest_path) as query:
        entity = query.get_entity("kb:component:synthetic-documentation-part")
        assert entity is not None
        base_snapshot = KnowledgeReferenceSnapshot.create(
            dataset_version=query.dataset_version,
            entity_key=entity.entity_key,
            entity_revision=entity.revision,
            entity_payload_sha256=entity.payload_sha256,
            snapshot_created_at_utc="2026-07-30T02:00:00Z",
        ).to_dict()
    base_snapshot["future_reader_hint"] = {
        "format_version": 2,
        "nested_unknown_fields": ["preserve", {"exactly": True}],
    }
    draft = PlantDesignProjectDraft.blank(project_name="KB-00 synthetic snapshot project")
    draft.canonical_construct_runtime = {
        "canonical_record_bytes_hex": "00010203a0ff",
        "fasta_bytes_hex": "10111213",
        "genbank_bytes_hex": "20212223",
    }
    draft.canonical_available = True
    payload = attach_snapshot_to_project_payload(draft.to_dict(), base_snapshot)
    return payload, base_snapshot
def _assert_exact_reopen(reopened: PlantDesignProjectDraft, expected_snapshot: dict) -> None:
    snapshot = snapshot_from_project_payload(reopened.to_dict())
    assert snapshot is not None
    assert snapshot.to_dict() == expected_snapshot
    assert reopened.canonical_construct_runtime == {
        "canonical_record_bytes_hex": "00010203a0ff",
        "fasta_bytes_hex": "10111213",
        "genbank_bytes_hex": "20212223",
    }


def test_snapshot_preserves_unknown_fields_for_forward_and_backward_compatibility() -> None:
    payload = {
        "kb_contract_version": "KB00-1.0-draft",
        "kb_dataset_version": "kb00-synthetic-v0.1.0",
        "entity_key": "kb:component:synthetic-documentation-part",
        "entity_revision": 1,
        "entity_payload_sha256": "a" * 64,
        "selected_sequence_sha256": "",
        "snapshot_created_at_utc": "2026-07-30T02:00:00Z",
        "future_scalar": "retained",
        "future_nested": {"values": [1, 2, 3]},
    }
    original = copy.deepcopy(payload)
    snapshot = KnowledgeReferenceSnapshot.from_mapping(payload)
    assert snapshot.to_dict() == original
    payload["future_nested"]["values"].append(4)
    assert snapshot.to_dict() == original


def test_json_project_repository_cold_reopen_preserves_snapshot_and_canonical_bytes(
    tmp_path: Path,
) -> None:
    payload, expected_snapshot = _project_payload_with_snapshot(tmp_path)
    storage = tmp_path / "json-projects"
    repository = PlantProjectDraftRepository(storage)
    saved = repository.save(payload)
    reopened = PlantProjectDraftRepository(storage).load(saved.project_id)
    _assert_exact_reopen(reopened, expected_snapshot)


def test_sqlite_project_history_cold_reopen_preserves_same_snapshot_and_canonical_bytes(
    tmp_path: Path,
) -> None:
    payload, expected_snapshot = _project_payload_with_snapshot(tmp_path)
    database_path = tmp_path / "project-history.sqlite"
    repository = _sqlite_project_repository(database_path)
    saved = repository.save(payload)
    reopened = SqlitePlantProjectDraftRepository(database_path).load(saved.project_id)
    _assert_exact_reopen(reopened, expected_snapshot)


def test_saved_snapshot_comparison_never_rewrites_project_snapshot(tmp_path: Path) -> None:
    payload, expected_snapshot = _project_payload_with_snapshot(tmp_path)
    saved_snapshot = snapshot_from_project_payload(payload)
    assert saved_snapshot is not None
    release = build_synthetic_release(tmp_path / "comparison-release")
    with open_knowledge_base(release.database_path, release.manifest_path) as query:
        comparison = query.compare_project_snapshot(saved_snapshot)
        assert comparison.status == "current"
    assert snapshot_from_project_payload(payload).to_dict() == expected_snapshot
    assert "registry_component_id" not in expected_snapshot
    assert "registry_id" not in expected_snapshot
