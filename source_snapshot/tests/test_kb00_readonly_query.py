from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from services.knowledge_base.errors import KnowledgeResourceError
from services.knowledge_base.reader import (
    KnowledgeQueryV0,
    open_knowledge_base,
    open_packaged_knowledge_base,
)
from services.knowledge_base.snapshot import KnowledgeReferenceSnapshot
from tests.kb00_helpers import build_synthetic_release


ROOT = Path(__file__).resolve().parents[1]


def _rewrite_manifest_hash(manifest_path: Path, database_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["sha256"] = hashlib.sha256(database_path.read_bytes()).hexdigest()
    manifest["database"]["size_bytes"] = database_path.stat().st_size
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_verified_reader_is_read_only_and_has_no_write_api(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    before = result.database_path.read_bytes()
    with open_knowledge_base(result.database_path, result.manifest_path) as query:
        assert isinstance(query, KnowledgeQueryV0)
        assert query.contract_version == "KnowledgeQueryV0"
        assert query.dataset_version == "kb00-synthetic-v0.1.0"
        public_names = {name for name in dir(query) if not name.startswith("_")}
        assert not public_names & {"write", "insert", "update", "delete", "commit", "execute"}
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            query._connection.execute("UPDATE kb_entity SET canonical_label='changed'")
    assert result.database_path.read_bytes() == before


def test_repository_packaged_release_opens_through_runtime_resolver() -> None:
    with open_packaged_knowledge_base(ROOT) as query:
        assert query.dataset_version == "kb00-synthetic-v0.1.0"
        assert [claim.evidence_claim_key for claim in query.search_claims("synthetic")] == [
            "kb:evidence-claim:synthetic-reviewed-fact"
        ]


def test_default_search_returns_only_approved_runtime_fact_with_complete_context(
    tmp_path: Path,
) -> None:
    result = build_synthetic_release(tmp_path / "release")
    with open_knowledge_base(result.database_path, result.manifest_path) as query:
        claims = query.search_claims("synthetic", limit=20)
        assert [claim.evidence_claim_key for claim in claims] == [
            "kb:evidence-claim:synthetic-reviewed-fact"
        ]
        claim = claims[0]
        assert claim.fact_class == "FACT"
        assert claim.review_status == "HUMAN_APPROVED"
        assert claim.runtime_eligible is True
        assert claim.registry_eligible is False
        assert claim.organism_context_status == "KNOWN"
        assert claim.tissue_context_status == "KNOWN"
        assert claim.experiment_context_status == "KNOWN"
        assert claim.sources[0].source_reference_key == "kb:source-reference:synthetic-review-note"
        assert claim.sources[0].location_type == "SECTION"
        assert claim.scopes[0].applicability_scope_key == "kb:applicability-scope:synthetic-context"
        assert claim.dataset_version == query.dataset_version
        assert len(claim.entity_payload_sha256) == 64

        filtered = query.search_claims(
            "synthetic",
            organism_key="kb:organism:synthetic-plant-context",
            tissue_key="kb:tissue:synthetic-plant-context",
            experiment_key="kb:experiment:synthetic-documentation-context",
        )
        assert filtered == claims
        assert query.search_claims("synthetic", organism_key="kb:organism:missing") == ()


def test_explicit_audit_queries_preserve_epistemic_classes_conflicts_and_limitations(
    tmp_path: Path,
) -> None:
    result = build_synthetic_release(tmp_path / "release")
    with open_knowledge_base(result.database_path, result.manifest_path) as query:
        derivation = query.get_claim("kb:evidence-claim:synthetic-derivation")
        inference = query.get_claim("kb:evidence-claim:synthetic-inference")
        unknown = query.get_claim("kb:evidence-claim:synthetic-unknown")
        assert derivation is not None and derivation.fact_class == "DERIVATION"
        assert inference is not None and inference.fact_class == "INFERENCE"
        assert inference.limitations[0].severity == "BLOCKING"
        assert unknown is not None and unknown.fact_class == "UNKNOWN"
        assert unknown.object_value_text is None
        assert unknown.unknown_reason

        conflicts = query.list_conflicts("kb:component:synthetic-documentation-part")
        assert {claim.fact_class for claim in conflicts} == {"FACT"}
        assert {claim.evidence_claim_key for claim in conflicts} == {
            "kb:evidence-claim:synthetic-conflict-a",
            "kb:evidence-claim:synthetic-conflict-b",
        }
        assert all(claim.conflicts[0].resolution_status == "OPEN" for claim in conflicts)
        assert [claim.evidence_claim_key for claim in query.list_unknowns()] == [
            "kb:evidence-claim:synthetic-unknown"
        ]
        assert [claim.evidence_claim_key for claim in query.list_component_evidence(
            "kb:component:synthetic-documentation-part"
        )] == ["kb:evidence-claim:synthetic-reviewed-fact"]


def test_entity_case_graph_and_snapshot_comparison_are_read_only(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    with open_knowledge_base(result.database_path, result.manifest_path) as query:
        component = query.get_entity("kb:component:synthetic-documentation-part")
        assert component is not None
        graph = query.get_design_case_graph("kb:design-case:synthetic-documentation-case")
        assert graph is not None
        assert graph.construct_keys == ("kb:construct:synthetic-documentation-record",)
        assert graph.transcription_unit_keys == (
            "kb:transcription-unit:synthetic-documentation-unit",
        )
        assert graph.component_keys == ("kb:component:synthetic-documentation-part",)

        snapshot = KnowledgeReferenceSnapshot.create(
            dataset_version=query.dataset_version,
            entity_key=component.entity_key,
            entity_revision=component.revision,
            entity_payload_sha256=component.payload_sha256,
            snapshot_created_at_utc="2026-07-30T01:00:00Z",
        )
        comparison = query.compare_project_snapshot(snapshot)
        assert comparison.status == "current"
        missing = KnowledgeReferenceSnapshot.create(
            dataset_version=query.dataset_version,
            entity_key="kb:component:missing-synthetic-record",
            entity_revision=1,
            entity_payload_sha256="f" * 64,
            snapshot_created_at_utc="2026-07-30T01:00:00Z",
        )
        assert query.compare_project_snapshot(missing).status == "missing"


def test_missing_database_fails_without_creating_any_file(tmp_path: Path) -> None:
    database = tmp_path / "missing" / "kb_v0.sqlite3"
    manifest = tmp_path / "missing" / "manifest.json"
    with pytest.raises(KnowledgeResourceError, match="knowledge database is missing"):
        open_knowledge_base(database, manifest)
    assert not database.exists()
    assert not manifest.exists()
    assert not database.parent.exists()


def test_hash_mismatch_rejects_before_sqlite_open_without_byte_change(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["database"]["sha256"] = "0" * 64
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = result.database_path.read_bytes()
    with pytest.raises(KnowledgeResourceError, match="SHA-256 differs"):
        open_knowledge_base(result.database_path, result.manifest_path)
    assert result.database_path.read_bytes() == before


def test_corrupt_and_future_database_reject_without_writes(tmp_path: Path) -> None:
    corrupt = build_synthetic_release(tmp_path / "corrupt")
    corrupt_bytes = bytearray(corrupt.database_path.read_bytes())
    corrupt_bytes[0:16] = b"not-a-sqlite-db!"
    corrupt.database_path.write_bytes(corrupt_bytes)
    _rewrite_manifest_hash(corrupt.manifest_path, corrupt.database_path)
    before_corrupt = corrupt.database_path.read_bytes()
    with pytest.raises(KnowledgeResourceError, match="read-only open failed"):
        open_knowledge_base(corrupt.database_path, corrupt.manifest_path)
    assert corrupt.database_path.read_bytes() == before_corrupt

    future = build_synthetic_release(tmp_path / "future")
    connection = sqlite3.connect(future.database_path)
    try:
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    finally:
        connection.close()
    _rewrite_manifest_hash(future.manifest_path, future.database_path)
    before_future = future.database_path.read_bytes()
    with pytest.raises(KnowledgeResourceError, match="future user_version 2"):
        open_knowledge_base(future.database_path, future.manifest_path)
    assert future.database_path.read_bytes() == before_future


def test_manifest_release_mismatch_rejects_verified_database(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_version"] = "kb00-synthetic-v0.2.0"
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = result.database_path.read_bytes()
    with pytest.raises(KnowledgeResourceError, match="release metadata differs"):
        open_knowledge_base(result.database_path, result.manifest_path)
    assert result.database_path.read_bytes() == before
