import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services import design_saver
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sequence TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS project_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT,
    version INTEGER,
    chassis TEXT,
    design_data TEXT,
    created_at TEXT,
    creator TEXT,
    status TEXT
);
"""


def _design_saver_roundtrip_db_path(filename: str) -> str:
    return str(repo_local_sqlite_db_path(".pytest_tmp_r80_design_saver_dbs", filename))


def test_design_saver_round_trip_persists_primer_context_fields(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_roundtrip.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    session = DesignSession(
        step=4,
        gene_name="GFP",
        original_seq="ATGAAATTTCCCTAA",
        optimized_seq="ATGCCCAAATTTTAA",
        host="E.coli BL21(DE3)",
        cloning_method="Gibson",
        primer_context_host="E.coli BL21(DE3)",
        primer_context_seq_hash="abc123seqhash",
        primers=[{"name": "Fwd", "sequence": "ATGCCC"}],
        frame={
            "final_sequence": "ATGCCCAAATTTTAA",
            "gc_content": 50.0,
            "vector_suggestion": "pET-28a",
            "success": True,
            "features": [],
        },
    )

    ok, saved_name = design_saver.save_wizard_design(session)
    assert ok is True

    loaded_ok, loaded = design_saver.load_wizard_design(saved_name)
    assert loaded_ok is True
    assert loaded.primer_context_host == "E.coli BL21(DE3)"
    assert loaded.primer_context_seq_hash == "abc123seqhash"


def test_design_saver_loads_legacy_payload_without_primer_context_fields(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_legacy.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        legacy_name = "Legacy GFP Design"
        legacy_payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "tag": "",
            "cloning_method": "Gibson",
            "vector": "pET-28a",
            "seq_len": 15,
            "gc_content": 50.0,
            "sequence": "ATGCCCAAATTTTAA",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {
                "final_sequence": "ATGCCCAAATTTTAA",
                "gc_content": 50.0,
                "vector_suggestion": "pET-28a",
                "success": True,
                "features": [],
            },
            "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            "codon_report": {},
            "validation_results": [],
            "method": "Expression Wizard",
            "step_reached": 4,
            "saved_at": "2026-04-08T12:00:00",
        }
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                legacy_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(legacy_payload),
                "2026-04-08 12:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded_ok, loaded = design_saver.load_wizard_design(legacy_name)
    assert loaded_ok is True
    assert loaded.primer_context_host == ""
    assert loaded.primer_context_seq_hash == ""


def test_load_wizard_design_resume_step_uses_artifact_safe_cap(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_resume_cap.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Resume Cap Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {
                "success": True,
                "final_sequence": "ATGCCCAAATTTTAA",
                "features": [],
            },
            "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            "validation_results": [],
            "step_reached": 6,
        }
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-08 12:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded_ok, loaded = design_saver.load_wizard_design(project_name)
    assert loaded_ok is True
    assert loaded.step == 5



def test_load_wizard_design_resume_step_allows_step6_when_validation_exists(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_resume_step6.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Resume Step6 Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {
                "success": True,
                "final_sequence": "ATGCCCAAATTTTAA",
                "features": [],
            },
            "validation_results": [{"severity": "warn", "message": "ok"}],
            "step_reached": 5,
        }
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-08 12:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded_ok, loaded = design_saver.load_wizard_design(project_name)
    assert loaded_ok is True
    assert loaded.step == 6


@pytest.mark.parametrize(
    ("payload", "expected_step"),
    [
        ({}, 1),
        ({"original_seq": "ATGAAATTTCCCTAA"}, 2),
        (
            {
                "original_seq": "ATGAAATTTCCCTAA",
                "host": "E.coli BL21(DE3)",
            },
            3,
        ),
        (
            {
                "original_seq": "ATGAAATTTCCCTAA",
                "host": "E.coli BL21(DE3)",
                "frame": {"success": True, "final_sequence": "ATGCCCAAATTTTAA", "features": []},
            },
            4,
        ),
        (
            {
                "original_seq": "ATGAAATTTCCCTAA",
                "host": "E.coli BL21(DE3)",
                "frame": {"success": True, "final_sequence": "ATGCCCAAATTTTAA", "features": []},
                "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            },
            5,
        ),
        (
            {
                "original_seq": "ATGAAATTTCCCTAA",
                "host": "E.coli BL21(DE3)",
                "frame": {"success": True, "final_sequence": "ATGCCCAAATTTTAA", "features": []},
                "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
                "validation_results": [{"severity": "warn", "message": "ok"}],
            },
            6,
        ),
    ],
)
def test_artifact_reopen_step_ladder(payload, expected_step):
    assert design_saver._artifact_safe_max_step(payload) == expected_step


def _find_summary_by_name(summaries, name):
    return next((summary for summary in summaries if summary.get("name") == name), None)


def _assert_design_absent(load_key):
    summaries = design_saver.query_saved_design_summaries()
    assert _find_summary_by_name(summaries, load_key) is None
    assert design_saver.query_saved_design_detail(load_key) == {}

    loaded_ok, loaded_result = design_saver.load_wizard_design(load_key)
    assert loaded_ok is False
    assert f"Project not found: {load_key}" == loaded_result


def test_saved_design_lifecycle_uses_consistent_summary_detail_load_delete_keys(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("saved_design_lifecycle.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    session = DesignSession(
        step=5,
        gene_name="Lifecycle GFP",
        original_seq="ATGAAATTTCCCTAA",
        optimized_seq="ATGCCCAAATTTTAA",
        host="E.coli BL21(DE3)",
        tag="His6-tag (N-term)",
        cloning_method="Gibson",
        primer_context_host="E.coli BL21(DE3)",
        primer_context_seq_hash="lifecycle-hash",
        primers=[{"name": "Lifecycle Fwd", "sequence": "ATGCCC"}],
        codon_report={"success": True, "after": {"cai": 0.91}},
        frame={
            "success": True,
            "final_sequence": "ATGCCCAAATTTTAA",
            "gc_content": 46.7,
            "vector_suggestion": "pET-28a",
            "features": [{"name": "Lifecycle GFP", "start": 1, "end": 15}],
        },
    )

    saved_ok, saved_name = design_saver.save_wizard_design(session)
    assert saved_ok is True

    summaries = design_saver.query_saved_design_summaries()
    summary = _find_summary_by_name(summaries, saved_name)
    assert summary is not None
    assert summary["design_id"] == saved_name["design_id"]
    assert summary["name"] == saved_name
    assert summary["load_key"] == saved_name["design_id"]
    assert summary["delete_key"] == saved_name["design_id"]
    assert summary["source"] == "sequences"

    detail = design_saver.query_saved_design_detail(summary["load_key"])
    assert detail["design_id"] == saved_name["design_id"]
    assert detail["name"] == saved_name
    assert detail["load_key"] == saved_name["design_id"]
    assert detail["summary"]["delete_key"] == saved_name["design_id"]
    assert detail["design_data"]["gene_name"] == session.gene_name
    assert detail["design_data"]["host"] == session.host
    assert detail["design_data"]["sequence"] == session.frame["final_sequence"]
    assert detail["design_data"]["primer_context_seq_hash"] == session.primer_context_seq_hash

    loaded_ok, loaded = design_saver.load_wizard_design(summary["load_key"])
    assert loaded_ok is True
    assert loaded.gene_name == session.gene_name
    assert loaded.host == session.host
    assert loaded.original_seq == session.original_seq
    assert loaded.optimized_seq == session.optimized_seq
    assert loaded.frame.get("final_sequence") == session.frame["final_sequence"]
    assert loaded.primers == session.primers
    assert loaded.primer_context_seq_hash == session.primer_context_seq_hash

    deleted_ok, deleted_key = design_saver.delete_wizard_design(summary["delete_key"])
    assert deleted_ok is True
    assert deleted_key == saved_name["design_id"]
    _assert_design_absent(summary["load_key"])


def test_saved_design_lifecycle_allows_legacy_name_delete_key(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("saved_design_legacy_delete.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    session = DesignSession(
        step=3,
        gene_name="Legacy Delete GFP",
        original_seq="ATGAAATTTCCCTAA",
        optimized_seq="ATGCCCAAATTTTAA",
        host="E.coli BL21(DE3)",
        frame={
            "success": True,
            "final_sequence": "ATGCCCAAATTTTAA",
            "gc_content": 46.7,
            "features": [],
        },
    )

    saved_ok, saved_name = design_saver.save_wizard_design(session)
    assert saved_ok is True
    assert _find_summary_by_name(design_saver.query_saved_design_summaries(), saved_name) is not None

    deleted_ok, deleted_key = design_saver.delete_wizard_design(saved_name)
    assert deleted_ok is True
    assert deleted_key == saved_name
    _assert_design_absent(saved_name)


def test_sequence_only_fallback_lifecycle_uses_same_keys_until_delete(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("sequence_only_fallback_lifecycle.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    sequence_name = "Sequence Only Fallback"
    sequence = "ATGAAATTTCCCTAA"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) "
            "VALUES (?, ?, ?, ?, ?)",
            (sequence_name, sequence, "Expression Wizard", "Legacy sequence-only design", "2026-04-08 12:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    summary = _find_summary_by_name(design_saver.query_saved_design_summaries(), sequence_name)
    assert summary is not None
    assert summary["load_key"] == sequence_name
    assert summary["delete_key"] == sequence_name
    assert summary["source"] == "sequences"

    detail = design_saver.query_saved_design_detail(summary["load_key"])
    assert detail["load_key"] == sequence_name
    assert detail["design_data"]["_sequence_only_fallback"] is True
    assert detail["design_data"]["original_seq"] == sequence
    assert detail["load_warnings"] == ["Sequence-only fallback; full design metadata is unavailable."]

    loaded_ok, loaded = design_saver.load_wizard_design(summary["load_key"])
    assert loaded_ok is True
    assert loaded.step == 1
    assert loaded.gene_name == sequence_name
    assert loaded.original_seq == sequence
    assert loaded.optimized_seq == sequence

    deleted_ok, deleted_key = design_saver.delete_wizard_design(summary["delete_key"])
    assert deleted_ok is True
    assert deleted_key == sequence_name
    _assert_design_absent(sequence_name)



def test_load_wizard_design_sequence_only_fallback_resumes_at_step1(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_sequence_only.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Sequence Only Design"
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGAAATTTCCCTAA",
                "Expression Wizard",
                "Sequence-only fallback",
                "2026-04-08 12:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded_ok, loaded = design_saver.load_wizard_design(project_name)
    assert loaded_ok is True
    assert loaded.step == 1
    assert loaded.original_seq == "ATGAAATTTCCCTAA"


def test_query_saved_design_summaries_returns_canonical_sequence_history_record(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_summary.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Canonical GFP Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "cloning_method": "Gibson",
            "vector": "pET-28a",
            "seq_len": 15,
            "gc_content": 50.0,
            "sequence": "ATGCCCAAATTTTAA",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {
                "success": True,
                "final_sequence": "ATGCCCAAATTTTAA",
                "features": [{"type": "CDS", "start": 1, "end": 15}],
            },
            "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            "validation_results": [],
            "method": "Expression Wizard",
            "step_reached": 4,
            "saved_at": "2026-04-02T11:00:00",
            "n_primers": 1,
            "n_issues": 0,
        }
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGCCCAAATTTTAA",
                "Expression Wizard",
                "Saved Expression Wizard design",
                "2026-04-02 11:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-02 11:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    summaries = design_saver.query_saved_design_summaries()

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["design_id"] == project_name
    assert summary["name"] == project_name
    assert summary["load_key"] == project_name
    assert summary["delete_key"] == project_name
    assert summary["gene"] == "GFP"
    assert summary["host"] == "E.coli BL21(DE3)"
    assert summary["type"] == "Expression Design"
    assert summary["saved_at"] == "2026-04-02T11:00:00"
    assert summary["created_at"] == "2026-04-02 11:00:00"
    assert summary["updated_at"] is None
    assert summary["sequence_length"] == 15
    assert summary["source"] == "sequences"
    assert summary["db_refs"] == {
        "sequences_name": project_name,
        "project_history_project_name": project_name,
        "sequence_date_added": "2026-04-02 11:00:00",
        "project_history_created_at": "2026-04-02 11:00:00",
        "source": "sequences",
    }
    assert summary["status"] == "saved"
    assert summary["metadata"]["gc_content"] == 50.0
    assert summary["metadata"]["step"] == 4
    assert summary["metadata"]["cloning_method"] == "Gibson"
    assert summary["metadata"]["vector"] == "pET-28a"
    assert summary["metadata"]["n_primers"] == 1
    assert summary["metadata"]["n_issues"] == 0
    assert summary["metadata"]["db_refs"] == {
        "sequences_name": project_name,
        "project_history_project_name": project_name,
        "sequence_date_added": "2026-04-02 11:00:00",
        "project_history_created_at": "2026-04-02 11:00:00",
        "source": "sequences",
    }
    assert summary["raw"]["sequence"] == "ATGCCCAAATTTTAA"
    assert summary["raw"]["project_history_data"]["gene_name"] == "GFP"


def test_query_saved_design_detail_returns_canonical_full_record(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_detail.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Detail GFP Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "cloning_method": "Gibson",
            "vector": "pET-28a",
            "seq_len": 15,
            "gc_content": 50.0,
            "sequence": "ATGCCCAAATTTTAA",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {
                "success": True,
                "final_sequence": "ATGCCCAAATTTTAA",
                "features": [{"type": "CDS", "start": 1, "end": 15}],
            },
            "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            "validation_results": [{"severity": "info", "message": "Ready"}],
            "method": "Expression Wizard",
            "step_reached": 6,
            "saved_at": "2026-04-02T11:00:00",
            "n_primers": 1,
            "n_issues": 1,
        }
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGCCCAAATTTTAA",
                "Expression Wizard",
                "Saved Expression Wizard design",
                "2026-04-02 11:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-02 11:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    detail = design_saver.query_saved_design_detail(project_name)

    assert detail["design_id"] == project_name
    assert detail["load_key"] == project_name
    assert detail["name"] == project_name
    assert detail["source"] == "sequences"
    assert detail["design_data"] == payload
    assert detail["sequence"] == "ATGCCCAAATTTTAA"
    assert detail["frame"] == payload["frame"]
    assert detail["validation_results"] == payload["validation_results"]
    assert detail["primers"] == payload["primers"]
    assert detail["can_load"] is True
    assert detail["load_warnings"] == []
    assert detail["summary"]["design_id"] == project_name
    assert detail["summary"]["sequence_length"] == 15
    assert detail["metadata"]["step"] == 6
    assert detail["metadata"]["db_refs"] == detail["db_refs"]
    assert detail["db_refs"] == {
        "sequences_name": project_name,
        "project_history_project_name": project_name,
        "sequence_date_added": "2026-04-02 11:00:00",
        "project_history_created_at": "2026-04-02 11:00:00",
        "source": "sequences",
    }


def test_query_saved_design_detail_sequence_only_fallback_matches_load_contract(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_detail_sequence_only.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Detail Sequence Only Design"
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGAAATTTCCCTAA",
                "Expression Wizard",
                "Sequence-only fallback",
                "2026-04-08 12:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    detail = design_saver.query_saved_design_detail(project_name)
    loaded_ok, loaded = design_saver.load_wizard_design(project_name)

    assert detail["design_id"] == project_name
    assert detail["load_key"] == project_name
    assert detail["source"] == "sequences"
    assert detail["sequence"] == "ATGAAATTTCCCTAA"
    assert detail["design_data"]["_sequence_only_fallback"] is True
    assert detail["design_data"]["original_seq"] == "ATGAAATTTCCCTAA"
    assert detail["frame"]["final_sequence"] == "ATGAAATTTCCCTAA"
    assert detail["primers"] == []
    assert detail["validation_results"] == []
    assert detail["can_load"] is True
    assert detail["load_warnings"] == ["Sequence-only fallback; full design metadata is unavailable."]
    assert detail["metadata"]["step"] == 1
    assert loaded_ok is True
    assert loaded.step == 1
    assert loaded.original_seq == "ATGAAATTTCCCTAA"


def test_query_saved_design_detail_returns_empty_record_when_missing(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_detail_missing.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    assert design_saver.query_saved_design_detail("Missing Design") == {}


def test_get_saved_design_rows_wraps_canonical_summaries_for_dashboard_compatibility(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_dashboard_rows.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Dashboard GFP Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "cloning_method": "Gibson",
            "vector": "pET-28a",
            "seq_len": 15,
            "gc_content": 50.0,
            "sequence": "ATGCCCAAATTTTAA",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {"success": True, "final_sequence": "ATGCCCAAATTTTAA", "features": []},
            "primers": [{"name": "Fwd", "sequence": "ATGCCC"}],
            "validation_results": [],
            "method": "Expression Wizard",
            "step_reached": 4,
            "n_primers": 1,
            "n_issues": 0,
        }
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGCCCAAATTTTAA",
                "Expression Wizard",
                "Saved Expression Wizard design",
                "2026-04-02 11:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-02 11:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    rows = design_saver.get_saved_design_rows()

    assert len(rows) == 1
    row = rows[0]
    assert row == {
        "Name": project_name,
        "Gene": "GFP",
        "Host": "E.coli BL21(DE3)",
        "Length (bp)": 15,
        "GC%": "50.0%",
        "Type": "Expression Design",
        "Saved": "2026-04-02 11:00",
        "_sequence": "ATGCCCAAATTTTAA",
        "_features": [],
        "_source": "sequences",
        "_load_key": project_name,
        "_delete_key": project_name,
        "_gene": "GFP",
        "_host": "E.coli BL21(DE3)",
        "_cloning": "Gibson",
        "_step": 4,
        "_vector": "pET-28a",
        "_n_primers": 1,
        "_n_issues": 0,
        "_gc": 50.0,
    }

def test_saved_design_identity_helpers_keep_legacy_key_compatibility():
    identity = design_saver.resolve_saved_design_identity(
        name="Legacy Compatible Design",
        source="sequences",
        sequences_name="Legacy Compatible Design",
        project_history_project_name="Legacy Compatible Design",
        sequence_date_added="2026-04-04 10:00:00",
        project_history_created_at="2026-04-04 10:00:00",
    )

    assert identity["design_id"] == "Legacy Compatible Design"
    assert identity["name"] == "Legacy Compatible Design"
    assert identity["load_key"] == "Legacy Compatible Design"
    assert identity["delete_key"] == "Legacy Compatible Design"
    assert identity["source"] == "sequences"
    assert identity["db_refs"] == {
        "sequences_name": "Legacy Compatible Design",
        "project_history_project_name": "Legacy Compatible Design",
        "sequence_date_added": "2026-04-04 10:00:00",
        "project_history_created_at": "2026-04-04 10:00:00",
        "source": "sequences",
    }
    assert design_saver.saved_design_load_key(identity) == "Legacy Compatible Design"
    assert design_saver.saved_design_delete_key(identity) == "Legacy Compatible Design"
    assert design_saver.saved_design_load_key("Legacy Compatible Design") == "Legacy Compatible Design"
    assert design_saver.saved_design_delete_key("Legacy Compatible Design") == "Legacy Compatible Design"


def test_load_and_delete_wizard_design_keep_legacy_string_key_contract(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_identity_keys.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "Legacy Key Design"
        payload = {
            "gene_name": "GFP",
            "host": "E.coli BL21(DE3)",
            "original_seq": "ATGAAATTTCCCTAA",
            "optimized_seq": "ATGCCCAAATTTTAA",
            "frame": {"success": True, "final_sequence": "ATGCCCAAATTTTAA", "features": []},
            "step_reached": 4,
        }
        conn.execute(
            "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
            (
                project_name,
                "ATGCCCAAATTTTAA",
                "Expression Wizard",
                "Saved Expression Wizard design",
                "2026-04-05 10:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "E.coli BL21(DE3)",
                json.dumps(payload),
                "2026-04-05 10:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded_ok, loaded = design_saver.load_wizard_design(project_name)
    assert loaded_ok is True
    assert loaded.gene_name == "GFP"

    deleted_ok, deleted_key = design_saver.delete_wizard_design(project_name)
    assert deleted_ok is True
    assert deleted_key == project_name

    conn = sqlite3.connect(str(db_path))
    try:
        remaining_sequences = conn.execute("SELECT COUNT(*) FROM sequences WHERE name = ?", (project_name,)).fetchone()[0]
        remaining_history = conn.execute(
            "SELECT COUNT(*) FROM project_history WHERE project_name = ?",
            (project_name,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert remaining_sequences == 0
    assert remaining_history == 0


def test_query_saved_design_summaries_project_history_only_fallback(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_summary_history_only.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        project_name = "History Only Design"
        payload = {
            "gene_name": "RFP",
            "host": "S. cerevisiae",
            "cloning_method": "Golden Gate",
            "vector": "pYES2",
            "seq_len": 12,
            "gc_content": 45.0,
            "sequence": "ATGAAACCCTAA",
            "original_seq": "ATGAAACCCTAA",
            "frame": {"success": True, "final_sequence": "ATGAAACCCTAA", "features": []},
            "primers": [{"name": "Fwd", "sequence": "ATGAAA"}],
            "validation_results": [],
            "method": "Expression Wizard",
            "step_reached": 5,
        }
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_name,
                1,
                "S. cerevisiae",
                json.dumps(payload),
                "2026-04-03 12:30:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    summaries = design_saver.query_saved_design_summaries()
    rows = design_saver.get_saved_design_rows()

    assert len(summaries) == 1
    assert summaries[0]["source"] == "project_history"
    assert summaries[0]["design_id"] == project_name
    assert summaries[0]["name"] == project_name
    assert summaries[0]["load_key"] == project_name
    assert summaries[0]["delete_key"] == project_name
    assert summaries[0]["db_refs"] == {
        "sequences_name": "",
        "project_history_project_name": project_name,
        "sequence_date_added": "",
        "project_history_created_at": "2026-04-03 12:30:00",
        "source": "project_history",
    }
    assert summaries[0]["metadata"]["db_refs"] == {
        "sequences_name": "",
        "project_history_project_name": project_name,
        "sequence_date_added": "",
        "project_history_created_at": "2026-04-03 12:30:00",
        "source": "project_history",
    }
    assert summaries[0]["gene"] == "RFP"
    assert summaries[0]["host"] == "S. cerevisiae"
    assert summaries[0]["type"] == "Expression Wizard"
    assert summaries[0]["sequence_length"] == 12
    assert summaries[0]["status"] == "saved"
    assert rows[0]["Name"] == project_name
    assert rows[0]["Gene"] == "RFP"
    assert rows[0]["Host"] == "S. cerevisiae"
    assert rows[0]["Type"] == "Expression Wizard"
    assert rows[0]["Saved"] == "2026-04-03 12:30"
    assert rows[0]["_source"] == "project_history"
    assert rows[0]["_load_key"] == project_name
    assert rows[0]["_delete_key"] == project_name


def test_query_saved_design_summaries_filters_and_sorts_canonical_summaries(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_query_contract.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    records = [
        {
            "name": "Alpha Expression Design",
            "gene": "GFP",
            "host": "E.coli BL21(DE3)",
            "category": "Expression Wizard",
            "sequence": "ATGAAATTTCCCTAA",
            "saved_at": "2026-04-03T09:00:00",
            "date_added": "2026-04-03 09:00:00",
        },
        {
            "name": "Beta Vector Design",
            "gene": "RFP",
            "host": "S. cerevisiae",
            "category": "Vector",
            "sequence": "ATG" + "A" * 5400 + "TAA",
            "saved_at": "2026-04-01T08:00:00",
            "date_added": "2026-04-01 08:00:00",
        },
        {
            "name": "Gamma Sequence Design",
            "gene": "LacZ",
            "host": "B. subtilis",
            "category": "Synthetic Fragment",
            "sequence": "ATGAAACCCTAA",
            "saved_at": "2026-04-02T10:00:00",
            "date_added": "2026-04-02 10:00:00",
        },
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        for record in records:
            payload = {
                "gene_name": record["gene"],
                "host": record["host"],
                "sequence": record["sequence"],
                "original_seq": record["sequence"],
                "frame": {"success": True, "final_sequence": record["sequence"], "features": []},
                "method": "Expression Wizard",
                "step_reached": 4,
                "saved_at": record["saved_at"],
            }
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (
                    record["name"],
                    record["sequence"],
                    record["category"],
                    "Saved design query contract fixture",
                    record["date_added"],
                ),
            )
            conn.execute(
                "INSERT INTO project_history "
                "(project_name, version, chassis, design_data, created_at, creator, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record["name"],
                    1,
                    record["host"],
                    json.dumps(payload),
                    record["date_added"],
                    "Expression Wizard",
                    "saved",
                ),
            )
        conn.commit()
    finally:
        conn.close()

    newest = design_saver.query_saved_design_summaries()
    oldest = design_saver.query_saved_design_summaries(sort_order="asc")
    gene_matches = design_saver.query_saved_design_summaries(search="lac")
    host_matches = design_saver.query_saved_design_summaries(search="cerevisiae")
    type_search_matches = design_saver.query_saved_design_summaries(search="vector")
    type_filter_matches = design_saver.query_saved_design_summaries(types="Expression Design")

    assert [summary["name"] for summary in newest] == [
        "Alpha Expression Design",
        "Gamma Sequence Design",
        "Beta Vector Design",
    ]
    assert [summary["name"] for summary in oldest] == [
        "Beta Vector Design",
        "Gamma Sequence Design",
        "Alpha Expression Design",
    ]
    assert [summary["name"] for summary in gene_matches] == ["Gamma Sequence Design"]
    assert [summary["name"] for summary in host_matches] == ["Beta Vector Design"]
    assert [summary["name"] for summary in type_search_matches] == ["Beta Vector Design"]
    assert [summary["name"] for summary in type_filter_matches] == ["Alpha Expression Design"]


def test_get_saved_design_rows_accepts_query_contract_without_changing_row_shape(monkeypatch):
    db_path = _design_saver_roundtrip_db_path("design_saver_query_rows.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        for name, gene, saved_at in [
            ("Early GFP Design", "GFP", "2026-04-01T08:00:00"),
            ("Late RFP Design", "RFP", "2026-04-02T09:00:00"),
        ]:
            created_at = saved_at.replace("T", " ")
            payload = {
                "gene_name": gene,
                "host": "E.coli BL21(DE3)",
                "sequence": "ATGAAATTTCCCTAA",
                "original_seq": "ATGAAATTTCCCTAA",
                "frame": {"success": True, "final_sequence": "ATGAAATTTCCCTAA", "features": []},
                "method": "Expression Wizard",
                "step_reached": 4,
                "saved_at": saved_at,
            }
            conn.execute(
                "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
                (name, "ATGAAATTTCCCTAA", "Expression Wizard", "Saved design", created_at),
            )
            conn.execute(
                "INSERT INTO project_history "
                "(project_name, version, chassis, design_data, created_at, creator, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, 1, "E.coli BL21(DE3)", json.dumps(payload), created_at, "Expression Wizard", "saved"),
            )
        conn.commit()
    finally:
        conn.close()

    rows = design_saver.get_saved_design_rows(search="rfp", types="Expression Design", sort_order="asc")

    assert len(rows) == 1
    assert rows[0]["Name"] == "Late RFP Design"
    assert rows[0]["Gene"] == "RFP"
    assert rows[0]["Type"] == "Expression Design"
    assert rows[0]["_load_key"] == "Late RFP Design"
    assert rows[0]["_delete_key"] == "Late RFP Design"
