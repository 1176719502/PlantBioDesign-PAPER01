import json
import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from core.design_session import DesignSession
from core.i18n import t as _t
from services import design_saver
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path
from views import Dashboard


MISLEADING_COPY = [
    "validation success",
    "successful cloning",
    "successful PCR",
    "successful expression",
    "ready for experiment",
    "experiment-ready",
    "production-ready",
    "yield prediction",
    "optimized pathway",
]
IMPORT_EXECUTION_COPY = [
    "enable_database_write=True",
    "execute_project_import_as_new_project",
    "Import Project",
    "Execute Import",
    "Confirm Import",
    "Import now",
    "Ready to import",
    "Ready for execution",
]


def _saved_design_immutable_db_path(filename: str) -> str:
    return str(repo_local_sqlite_db_path(".pytest_tmp_r80_saved_design_dbs", filename))


@pytest.fixture()
def isolated_db(monkeypatch):
    db_path = _saved_design_immutable_db_path("saved_designs.sqlite")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))
    return db_path


def _session(gene="GFP", host="E.coli BL21(DE3)", seq="ATG" * 20):
    return DesignSession(
        step=6,
        gene_name=gene,
        original_seq=seq,
        optimized_seq=seq,
        host=host,
        tag="His6-tag (C-term)",
        elements={"promoter_name": "T7", "rbs_name": "RBS", "terminator_name": "T7Te"},
        frame={"success": True, "final_sequence": seq, "gc_content": 50.0, "features": []},
        primers=[{"name": "p1", "sequence": "ATGC"}],
        validation_results=[{"level": "info", "message": "checked"}],
        cloning_method="Gibson Assembly",
        codon_report={"host": host},
    )


def _insert_legacy_record(db_path, name="Legacy Design", gene="LEG", host="Legacy host", seq="ATG" * 15):
    conn = sqlite3.connect(db_path)
    conn.execute(design_saver.PROJECT_HISTORY_TABLE_SQL)
    conn.execute(design_saver.SEQUENCES_TABLE_SQL)
    payload = {
        "gene_name": gene,
        "host": host,
        "original_seq": seq,
        "optimized_seq": seq,
        "sequence": seq,
        "frame": {"success": True, "final_sequence": seq, "features": []},
        "primers": [],
        "validation_results": [],
        "method": "Expression Wizard",
        "saved_at": "2026-01-01T10:00:00",
    }
    conn.execute(
        "INSERT INTO sequences (name, sequence, category, description, date_added) VALUES (?, ?, ?, ?, ?)",
        (name, seq, "Expression Wizard", "legacy", "2026-01-01 10:00:00"),
    )
    conn.execute(
        "INSERT INTO project_history (project_name, version, chassis, design_data, created_at, creator, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, 1, host, json.dumps(payload), "2026-01-01 10:00:00", "Expression Wizard", "saved"),
    )
    conn.commit()
    conn.close()


def test_new_save_payload_contains_immutable_identity(isolated_db):
    ok, result = design_saver.save_wizard_design(_session())

    assert ok is True
    assert result["design_id"]
    assert result["display_name"]

    detail = design_saver.query_saved_design_detail(result["design_id"])
    metadata = detail["metadata"]
    payload = detail["design_data"]

    assert payload["design_id"] == result["design_id"]
    assert payload["saved_design_version"] == 1
    assert payload["display_name"] == result["display_name"]
    assert payload["identity_source"] == "immutable_design_id"
    assert metadata["identity_source"] == "immutable_design_id"


def test_same_display_name_snapshots_have_distinct_internal_design_ids(isolated_db, monkeypatch):
    class FixedDatetime(design_saver.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(design_saver, "datetime", FixedDatetime)
    ok1, first = design_saver.save_wizard_design(_session())
    ok2, second = design_saver.save_wizard_design(_session())

    assert ok1 and ok2
    assert first["display_name"] == second["display_name"]
    assert first["design_id"] != second["design_id"]

    summaries = design_saver.query_saved_design_summaries()
    ids = {summary["design_id"] for summary in summaries}
    names = [summary["display_name"] for summary in summaries]

    assert first["design_id"] in ids
    assert second["design_id"] in ids
    assert names.count(first["display_name"]) == 2


def test_load_by_design_id_returns_correct_snapshot_and_traceability(isolated_db):
    ok1, first = design_saver.save_wizard_design(_session(gene="GFP", host="Host A", seq="ATG" * 20))
    ok2, second = design_saver.save_wizard_design(_session(gene="RFP", host="Host B", seq="ATG" * 22))
    assert ok1 and ok2

    ok, loaded = design_saver.load_wizard_design(second["design_id"])

    assert ok is True
    assert loaded.gene_name == "RFP"
    assert loaded.host == "Host B"
    assert loaded.original_seq == "ATG" * 22
    assert loaded.source_saved_design_id == second["design_id"]
    assert loaded.saved_design_metadata["identity_source"] == "immutable_design_id"

    from services.wizard_state_service import prepare_loaded_design_session

    state = {}
    summary = prepare_loaded_design_session(state, loaded)
    assert summary["sync_global_context"] is True
    assert state["wf_p1_name"] == "RFP"


def test_legacy_name_fallback_loads_without_design_id(isolated_db):
    _insert_legacy_record(isolated_db)

    summaries = design_saver.query_saved_design_summaries()
    legacy = summaries[0]
    assert legacy["design_id"] == "Legacy Design"
    assert legacy["identity_source"] == "legacy_name"

    ok, loaded = design_saver.load_wizard_design("Legacy Design")
    assert ok is True
    assert loaded.gene_name == "LEG"
    assert loaded.host == "Legacy host"
    assert loaded.saved_design_metadata["identity_source"] == "legacy_name"


def test_delete_by_design_id_removes_only_matching_duplicate_snapshot(isolated_db, monkeypatch):
    class FixedDatetime(design_saver.datetime):
        @classmethod
        def now(cls):
            return cls(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(design_saver, "datetime", FixedDatetime)
    _, first = design_saver.save_wizard_design(_session(seq="ATG" * 20))
    _, second = design_saver.save_wizard_design(_session(seq="ATG" * 21))

    ok, _ = design_saver.delete_wizard_design(first["design_id"])
    assert ok is True

    assert design_saver.query_saved_design_detail(first["design_id"]) == {}
    remaining = design_saver.query_saved_design_detail(second["design_id"])
    assert remaining["design_data"]["original_seq"] == "ATG" * 21


def test_dashboard_uses_design_id_selection_and_shared_load_helper():
    row = {"Name": "Same Name", "_load_key": "uuid-1", "_design_id": "uuid-1"}
    assert Dashboard._saved_design_option_key(row) == "uuid-1"
    assert Dashboard._saved_design_option_label(row) == "Same Name"

    dashboard_source = open(os.path.join(ROOT, "views", "Dashboard.py"), encoding="utf-8").read()
    assert "load_wizard_design(selected_key)" in dashboard_source
    assert "prepare_loaded_design_session" in dashboard_source

    copy = _t("dashboard.load_snapshot_clarification")
    assert "Saved design ID identifies a saved design record for loading and traceability." in copy
    assert "Expression Wizard design record subflow" in copy
    assert "without creating or selecting a linked Pathway Project context" in copy
    assert "Loading a saved design restores wizard inputs and outputs" not in copy


def test_no_misleading_or_import_execution_copy_added():
    modified_files = [
        os.path.join(ROOT, "services", "design_saver.py"),
        os.path.join(ROOT, "views", "Dashboard.py"),
        os.path.join(ROOT, "core", "design_session.py"),
        os.path.join(ROOT, "locales", "en.py"),
    ]
    combined = "\n".join(open(path, encoding="utf-8").read() for path in modified_files)

    for phrase in MISLEADING_COPY:
        assert phrase not in combined
    for phrase in IMPORT_EXECUTION_COPY:
        assert phrase not in combined
