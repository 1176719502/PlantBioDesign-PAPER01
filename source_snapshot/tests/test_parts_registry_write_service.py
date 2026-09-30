# -*- coding: utf-8 -*-
"""V2.4-R3 local parts registry write service tests."""
from __future__ import annotations

import hashlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_registry_repository as repo
from services import parts_registry_write_service as service


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "parts_registry_write.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _create_part() -> dict:
    result = service.create_local_part(
        local_id="part-local-001",
        part_type="Promoter",
        display_name="Local promoter documentation record",
        description="Local catalog metadata record for provenance review.",
    )
    assert result["ok"] is True
    return result["record"]


def test_create_local_part(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    record = _create_part()

    assert record["local_id"] == "part-local-001"
    assert record["part_type"] == "Promoter"
    assert record["display_name"] == "Local promoter documentation record"


def test_duplicate_local_id_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    duplicate = service.create_local_part(
        local_id="part-local-001",
        part_type="Promoter",
        display_name="Duplicate local record",
    )

    assert duplicate["ok"] is False
    assert "already exists" in duplicate["error"]
    assert len(repo.list_parts()) == 1


def test_invalid_part_type_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    result = service.create_local_part(
        local_id="part-local-001",
        part_type="host compatibility marker",
        display_name="Invalid documentation record",
    )

    assert result["ok"] is False
    assert repo.list_parts() == []


def test_add_metadata_only_version(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_version(
        part_local_id="part-local-001",
        version_label="metadata-only-v1",
        version_note="Version record preserves metadata without sequence.",
    )

    assert result["ok"] is True
    assert result["record"]["sequence"] is None
    assert result["record"]["sequence_hash"] is None
    assert result["record"]["sequence_hash_algorithm"] is None


def test_add_sequence_version_with_hash(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()
    sequence = "ATGCGTAA"
    digest = hashlib.sha256(sequence.encode("utf-8")).hexdigest()

    result = service.add_part_version(
        part_local_id="part-local-001",
        version_label="sequence-documented-v1",
        sequence=sequence,
        sequence_hash=digest,
        sequence_hash_algorithm="sha256",
        version_note="Sequence and hash are stored as documentation metadata only.",
    )

    assert result["ok"] is True
    assert result["record"]["sequence"] == sequence
    assert result["record"]["sequence_hash"] == digest
    assert result["record"]["sequence_hash_algorithm"] == "sha256"


def test_sequence_without_hash_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_version(
        part_local_id="part-local-001",
        version_label="invalid-sequence-without-hash",
        sequence="ATGCGTAA",
    )

    assert result["ok"] is False
    assert repo.list_versions_for_part("part-local-001") == []


def test_hash_without_sequence_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_version(
        part_local_id="part-local-001",
        version_label="invalid-hash-only",
        sequence_hash="abc123",
        sequence_hash_algorithm="sha256",
    )

    assert result["ok"] is False
    assert repo.list_versions_for_part("part-local-001") == []


def test_add_source(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_source(
        part_local_id="part-local-001",
        source_name="Local notebook",
        source_reference="NB-2026-06-12",
        organism_or_source_context="source context recorded from local documentation",
        provenance_note="Provenance context for human review.",
    )

    assert result["ok"] is True
    assert result["record"]["source_name"] == "Local notebook"
    assert repo.list_source_records("part-local-001")[0]["source_reference"] == "NB-2026-06-12"


def test_add_annotation(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_annotation(
        part_local_id="part-local-001",
        annotation_type="metadata completeness",
        annotation_text="Check source note before review.",
    )

    assert result["ok"] is True
    assert result["record"]["annotation_type"] == "metadata completeness"
    assert result["record"]["annotation_text"] == "Check source note before review."


def test_add_review_status(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_review_status(
        part_local_id="part-local-001",
        curation_status="metadata reviewed",
        human_review_status="human review documented",
        review_note="Curation status records documentation review only.",
        reviewer_name_or_initials="AB",
        reviewed_at="2026-06-12T10:00:00",
    )

    assert result["ok"] is True
    assert result["record"]["curation_status"] == "metadata reviewed"
    assert result["record"]["human_review_status"] == "human review documented"


def test_invalid_review_terms_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    curation_result = service.add_part_review_status(
        part_local_id="part-local-001",
        curation_status="ready for " + "execution",
        human_review_status="human review documented",
    )
    human_result = service.add_part_review_status(
        part_local_id="part-local-001",
        curation_status="metadata reviewed",
        human_review_status="validated " + "construct",
    )

    assert curation_result["ok"] is False
    assert human_result["ok"] is False
    assert repo.list_review_status_records("part-local-001") == []


def test_add_link(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_link(
        part_local_id="part-local-001",
        target_type="pathway_project",
        target_id="pathway-project-001",
        target_label="Pathway documentation project",
        link_note="Traceability note for local documentation review.",
        review_status="traceability reviewed",
    )

    assert result["ok"] is True
    assert result["record"]["target_type"] == "pathway_project"
    assert result["record"]["review_status"] == "traceability reviewed"


def test_invalid_link_target_type_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_link(
        part_local_id="part-local-001",
        target_type="host_compatibility_check",
        target_id="target-001",
        review_status="traceability reviewed",
    )

    assert result["ok"] is False
    assert repo.list_links_for_part("part-local-001") == []


def test_invalid_link_review_status_rejected(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _create_part()

    result = service.add_part_link(
        part_local_id="part-local-001",
        target_type="pathway_project",
        target_id="pathway-project-001",
        review_status="system selected",
    )

    assert result["ok"] is False
    assert repo.list_links_for_part("part-local-001") == []


def test_write_service_terms_stay_documentation_only():
    combined = "\n".join(
        [
            *repo.PART_TYPE_VOCABULARY,
            *repo.CURATION_STATUS_TERMS,
            *repo.HUMAN_REVIEW_STATUS_TERMS,
            *repo.PART_LINK_TARGET_TYPES,
            *repo.PART_LINK_REVIEW_STATUS_TERMS,
        ]
    ).lower()
    forbidden = [
        "recommend" + "ation",
        "yield " + "prediction",
        "optimized " + "pathway",
        "production" + "-ready",
        "experiment" + "-ready",
        "host " + "compatibility",
        "suit" + "ability",
        "scor" + "ing",
        "rank" + "ing",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
