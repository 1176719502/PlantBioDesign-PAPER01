from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from services.knowledge_base import builder
from services.knowledge_base.builder import build_knowledge_release, logical_dump_sha256
from services.knowledge_base.constants import APPLICATION_ID, ENTITY_TYPES, SCHEMA_VERSION
from services.knowledge_base.errors import KnowledgeBuildError
from tests.kb00_helpers import build_synthetic_release, cloned_synthetic_bundle


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_three_builds_are_byte_and_logically_deterministic(tmp_path: Path) -> None:
    results = [build_synthetic_release(tmp_path / f"build-{index}") for index in range(3)]
    assert len({result.database_sha256 for result in results}) == 1
    assert len({result.logical_dump_sha256 for result in results}) == 1
    assert len({result.build_manifest_sha256 for result in results}) == 1
    assert len({result.source_bundle_sha256 for result in results}) == 1
    assert len({result.database_path.read_bytes() for result in results}) == 1
    assert len({result.manifest_path.read_bytes() for result in results}) == 1
    assert len({result.provenance_path.read_bytes() for result in results}) == 1


def test_writer_provenance_records_pinned_environment_without_changing_manifest(
    tmp_path: Path,
) -> None:
    result = build_synthetic_release(tmp_path / "release")
    provenance = json.loads(result.provenance_path.read_text(encoding="utf-8"))

    assert provenance["writer_contract_version"] == "KB00-pinned-sqlite-writer-v1"
    assert provenance["required_sqlite_version"] == "3.49.1"
    assert provenance["writer_environment"]["sqlite_version"] == "3.49.1"
    assert provenance["writer_environment"]["sqlite_version_info"] == [3, 49, 1]
    assert provenance["writer_environment"]["sqlite_source_id"]
    assert provenance["writer_environment"]["sqlite_compile_options"]
    assert provenance["builder"]["schema_sha256"] == json.loads(
        result.manifest_path.read_text(encoding="utf-8")
    )["schema_sha256"]
    assert provenance["database"]["sha256"] == result.database_sha256
    assert provenance["database"]["logical_dump_sha256"] == result.logical_dump_sha256


def test_wrong_writer_fails_closed_before_output_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "wrong-writer"
    monkeypatch.setattr(builder.sqlite3, "sqlite_version", "3.51.0")
    monkeypatch.setattr(builder.sqlite3, "sqlite_version_info", (3, 51, 0))

    with pytest.raises(KnowledgeBuildError, match="KB00_PINNED_WRITER_ENVIRONMENT_MISMATCH"):
        build_synthetic_release(output)

    assert not output.exists()


def test_schema_checkout_line_endings_do_not_change_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_lf = builder.SCHEMA_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
    schema_crlf_path = tmp_path / "schema_v1_crlf.sql"
    schema_crlf_path.write_bytes(schema_lf.replace("\n", "\r\n").encode("utf-8"))

    expected = build_synthetic_release(tmp_path / "expected")
    monkeypatch.setattr(builder, "SCHEMA_PATH", schema_crlf_path)
    rebuilt = build_synthetic_release(tmp_path / "rebuilt")

    assert rebuilt.build_manifest_sha256 == expected.build_manifest_sha256
    assert rebuilt.logical_dump_sha256 == expected.logical_dump_sha256
    assert rebuilt.database_sha256 == expected.database_sha256
    assert rebuilt.database_path.read_bytes() == expected.database_path.read_bytes()
    assert rebuilt.manifest_path.read_bytes() == expected.manifest_path.read_bytes()


def test_packaged_release_matches_committed_input_rebuild_byte_for_byte(tmp_path: Path) -> None:
    rebuilt = build_synthetic_release(tmp_path / "rebuilt")
    packaged_root = Path(__file__).resolve().parents[1] / "data" / "knowledge_base_v0"
    packaged_database = packaged_root / "kb_v0.sqlite3"
    packaged_manifest_path = packaged_root / "manifest.json"
    packaged_manifest = json.loads(
        packaged_manifest_path.read_text(encoding="utf-8")
    )

    assert rebuilt.database_path.read_bytes() == packaged_database.read_bytes()
    assert rebuilt.manifest_path.read_bytes() == packaged_manifest_path.read_bytes()
    assert rebuilt.build_manifest_sha256 == packaged_manifest["build_manifest_sha256"]
    assert rebuilt.source_bundle_sha256 == packaged_manifest["source_bundle_sha256"]
    assert rebuilt.logical_dump_sha256 == logical_dump_sha256(packaged_database)
    assert rebuilt.logical_dump_sha256 == packaged_manifest["database"]["logical_dump_sha256"]


def test_release_schema_identity_integrity_and_entity_contract(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    connection = sqlite3.connect(result.database_path)
    try:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        release = connection.execute(
            "SELECT release_status, approved_by, approved_at_utc FROM kb_release"
        ).fetchall()
        assert len(release) == 1
        assert release[0][0] == "HUMAN_APPROVED"
        assert release[0][1:3] == (
            "kb00-synthetic-fixture-reviewer",
            "2026-07-30T00:00:00Z",
        )
        actual_types = {
            row[0] for row in connection.execute("SELECT DISTINCT entity_type FROM kb_entity")
        }
        assert actual_types == set(ENTITY_TYPES)
        assert connection.execute(
            "SELECT count(*) FROM kb_entity AS e LEFT JOIN kb_entity_revision AS r "
            "ON r.entity_key=e.entity_key AND r.revision=e.current_revision WHERE r.entity_key IS NULL"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM kb_evidence_claim AS c LEFT JOIN kb_claim_source AS s "
            "ON s.evidence_claim_key=c.evidence_claim_key GROUP BY c.evidence_claim_key "
            "HAVING count(s.source_reference_key)=0"
        ).fetchall() == []
    finally:
        connection.close()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["database"]["sha256"] == _sha256(result.database_path)
    assert manifest["database"]["size_bytes"] == result.database_path.stat().st_size
    assert manifest["record_counts"]["by_entity_type"].keys() == set(ENTITY_TYPES)
    assert manifest["copy_inventory"] == [
        {
            "classification": "synthetic_infrastructure_fixture",
            "contains_real_accessions": False,
            "contains_real_literature": False,
            "contains_real_sequences": False,
            "license_or_access_status": "INTERNAL_SYNTHETIC",
            "runtime_boundary": "documentation and review retrieval only",
        }
    ]


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda bundle: bundle.update({"future_field": True}), "unknown fields"),
        (lambda bundle: bundle.update({"schema_version": "kb00-import-future"}), "unsupported import schema_version"),
        (lambda bundle: bundle["records"]["paper"].append(dict(bundle["records"]["paper"][0])), "duplicate business key"),
        (lambda bundle: bundle["records"]["accession"].append({**bundle["records"]["accession"][0], "accession_key": "kb:accession:synthetic-duplicate-id"}), "semantic duplicate.*accession"),
        (lambda bundle: bundle["records"]["component"][0].update({"source_organism_key": "kb:organism:missing"}), "references missing entity"),
        (lambda bundle: bundle["records"]["component"][0].update({"source_organism_key": "kb:paper:synthetic-review-note"}), "references paper, expected organism"),
        (lambda bundle: bundle["records"]["evidence_claim"][0].update({"fact_class": "OPINION"}), "fact_class is invalid"),
        (lambda bundle: bundle["records"]["evidence_claim"][3].update({"unknown_reason": ""}), "UNKNOWN claim requires a reason"),
        (lambda bundle: bundle["records"]["evidence_claim"][0]["context"].update({"organism_status": "UNKNOWN"}), "organism_key does not match"),
        (lambda bundle: bundle["review_events"][0].update({"actor_type": "AI"}), "AI or import actor cannot"),
        (lambda bundle: bundle["relationships"].update({"claim_source": bundle["relationships"]["claim_source"][1:]}), "claims lack source locations"),
        (lambda bundle: bundle["records"]["evidence_claim"][2]["eligibility"].update({"runtime_eligible": True, "actor_type": "HUMAN", "decided_by": "fixture reviewer", "decided_at_utc": "2026-07-30T00:00:00Z"}), "runtime eligibility requires a human-approved FACT"),
        (lambda bundle: bundle["relationships"]["design_case_paper"][0].update({"relationship_type": "INVENTED"}), "relationship_type is invalid"),
        (lambda bundle: bundle["relationships"]["transcription_unit_component"][0].update({"start_zero_based": 10, "end_zero_based_exclusive": 5}), "component coordinates are invalid"),
        (lambda bundle: bundle["relationships"]["claim_conflict"].pop(), "conflict groups must retain at least two claims"),
        (lambda bundle: bundle["records"]["component_evidence"][0].update({"evidence_role": "INVENTED"}), "evidence_role is invalid"),
        (lambda bundle: bundle["records"]["limitation"][0].update({"limitation_type": "INVENTED"}), "limitation_type is invalid"),
        (lambda bundle: bundle["records"]["evidence_level"].append({**bundle["records"]["evidence_level"][0], "evidence_level_key": "kb:evidence-level:duplicate-code"}), "semantic duplicate.*level_code"),
    ],
)
def test_invalid_bundle_rejects_before_output_creation(
    tmp_path: Path,
    mutation,
    match: str,
) -> None:
    bundle = cloned_synthetic_bundle()
    mutation(bundle)
    output = tmp_path / "must-not-exist"
    with pytest.raises(KnowledgeBuildError, match=match):
        build_knowledge_release(bundle, output)
    assert not output.exists()


def test_registry_eligibility_requires_complete_human_review_inputs(tmp_path: Path) -> None:
    bundle = cloned_synthetic_bundle()
    claim = bundle["records"]["evidence_claim"][0]
    claim["eligibility"]["registry_eligible"] = True
    claim["eligibility"]["registry_candidate_reason"] = "Synthetic negative gate fixture."
    bundle["review_events"].append(
        {
            "review_event_key": "kbr:synthetic-reviewed-fact-registry",
            "entity_key": claim["evidence_claim_key"],
            "prior_status": "RUNTIME_ELIGIBLE",
            "new_status": "REGISTRY_ELIGIBLE",
            "actor_id": "kb00-synthetic-fixture-reviewer",
            "actor_type": "HUMAN",
            "reason": "Synthetic negative gate fixture.",
            "occurred_at_utc": "2026-07-30T00:00:00Z",
        }
    )
    with pytest.raises(KnowledgeBuildError, match="complete component sequence"):
        build_knowledge_release(bundle, tmp_path / "registry-incomplete")
    assert not (tmp_path / "registry-incomplete").exists()


def test_open_blocking_limitation_and_direct_conflict_reject_runtime_eligibility(
    tmp_path: Path,
) -> None:
    blocked = cloned_synthetic_bundle()
    inference = blocked["records"]["evidence_claim"][2]
    inference["fact_class"] = "FACT"
    inference["review"] = {
        "status": "HUMAN_APPROVED",
        "reviewed_by": "fixture reviewer",
        "reviewed_at_utc": "2026-07-30T00:00:00Z",
    }
    inference["evidence_level_key"] = "kb:evidence-level:fact-reviewed"
    inference["eligibility"] = {
        "runtime_eligible": True,
        "registry_eligible": False,
        "actor_type": "HUMAN",
        "decided_by": "fixture reviewer",
        "decided_at_utc": "2026-07-30T00:00:00Z",
        "registry_candidate_reason": "",
    }
    blocked["review_events"].extend(
        [
            {"review_event_key": "kbr:blocked-approved", "entity_key": inference["evidence_claim_key"], "prior_status": "PENDING_HUMAN_REVIEW", "new_status": "HUMAN_APPROVED", "actor_id": "fixture reviewer", "actor_type": "HUMAN", "reason": "negative fixture", "occurred_at_utc": "2026-07-30T00:00:00Z"},
            {"review_event_key": "kbr:blocked-runtime", "entity_key": inference["evidence_claim_key"], "prior_status": "HUMAN_APPROVED", "new_status": "RUNTIME_ELIGIBLE", "actor_id": "fixture reviewer", "actor_type": "HUMAN", "reason": "negative fixture", "occurred_at_utc": "2026-07-30T00:00:00Z"},
        ]
    )
    with pytest.raises(KnowledgeBuildError, match="open blocking limitation"):
        build_knowledge_release(blocked, tmp_path / "blocked")

    conflicted = cloned_synthetic_bundle()
    claim = conflicted["records"]["evidence_claim"][4]
    claim["evidence_level_key"] = "kb:evidence-level:fact-reviewed"
    claim["eligibility"] = {
        "runtime_eligible": True,
        "registry_eligible": False,
        "actor_type": "HUMAN",
        "decided_by": "fixture reviewer",
        "decided_at_utc": "2026-07-30T00:00:00Z",
        "registry_candidate_reason": "",
    }
    conflicted["review_events"].append(
        {"review_event_key": "kbr:conflicted-runtime", "entity_key": claim["evidence_claim_key"], "prior_status": "HUMAN_APPROVED", "new_status": "RUNTIME_ELIGIBLE", "actor_id": "fixture reviewer", "actor_type": "HUMAN", "reason": "negative fixture", "occurred_at_utc": "2026-07-30T00:00:00Z"}
    )
    with pytest.raises(KnowledgeBuildError, match="open direct conflict"):
        build_knowledge_release(conflicted, tmp_path / "conflicted")


def test_released_revision_source_and_review_rows_are_append_only(tmp_path: Path) -> None:
    result = build_synthetic_release(tmp_path / "release")
    connection = sqlite3.connect(result.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="source_reference identity is immutable"):
            connection.execute("UPDATE kb_source_reference SET provider='changed'")
        with pytest.raises(sqlite3.IntegrityError, match="entity revisions are append-only"):
            connection.execute("UPDATE kb_entity_revision SET change_reason='changed'")
        with pytest.raises(sqlite3.IntegrityError, match="review events cannot be deleted"):
            connection.execute("DELETE FROM kb_review_event")
        connection.rollback()

        key = "kb:component:synthetic-documentation-part"
        prior = connection.execute(
            "SELECT payload_json, payload_sha256 FROM kb_entity_revision WHERE entity_key=? AND revision=1",
            (key,),
        ).fetchone()
        connection.execute(
            "INSERT INTO kb_entity_revision VALUES (?, 2, ?, ?, ?, ?, 1, ?, ?, ?)",
            (
                key,
                "kb:release:synthetic-v0-1-0",
                prior[0],
                prior[1],
                "synthetic revision test",
                "fixture reviewer",
                "HUMAN",
                "2026-07-30T00:00:00Z",
            ),
        )
        connection.execute(
            "UPDATE kb_entity SET current_revision=2, lifecycle_status='RETIRED' WHERE entity_key=?",
            (key,),
        )
        connection.commit()
        assert connection.execute(
            "SELECT count(*) FROM kb_component_evidence WHERE component_key=?", (key,)
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_fault_before_promotion_preserves_previous_release_and_quarantines_candidate(
    tmp_path: Path,
) -> None:
    output = tmp_path / "atomic"
    first = build_synthetic_release(output)
    before_database = first.database_path.read_bytes()
    before_manifest = first.manifest_path.read_bytes()
    with pytest.raises(KnowledgeBuildError, match="injected fault"):
        build_knowledge_release(
            cloned_synthetic_bundle(),
            output,
            fault_after_database_validation=True,
        )
    assert first.database_path.read_bytes() == before_database
    assert first.manifest_path.read_bytes() == before_manifest
    assert (output / ".kb_v0.sqlite3.failed").is_file()
    assert not (output / ".kb_v0.sqlite3.building").exists()
