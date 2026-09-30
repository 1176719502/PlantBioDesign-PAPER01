import os
import sqlite3
import sys
from contextlib import contextmanager

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from core.design_session import DesignSession
from core.session_keys import SK
from services import design_saver
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path
import views.Dashboard as dashboard


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


def _restoration_stability_db_path(filename: str) -> str:
    return str(repo_local_sqlite_db_path(".pytest_tmp_r80_restoration_dbs", filename))


class _FakeColumnConfig:
    @staticmethod
    def TextColumn(*_args, **_kwargs):
        return {"kind": "text"}

    @staticmethod
    def NumberColumn(*_args, **_kwargs):
        return {"kind": "number"}


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.button_values = {}
        self.text_input_values = {}
        self.selectbox_values = {}
        self.column_config = _FakeColumnConfig()

    def markdown(self, *_args, **_kwargs):
        return None

    def text_input(self, _label, key=None, placeholder=None, **_kwargs):
        value = self.text_input_values.get(key, self.session_state.get(key, ""))
        if key is not None:
            self.session_state[key] = value
        return value

    def selectbox(self, _label, options, key=None, index=0, **_kwargs):
        if key in self.selectbox_values:
            value = self.selectbox_values[key]
        elif key is not None and self.session_state.get(key) in options:
            value = self.session_state[key]
        else:
            value = options[index] if options else None
        if key is not None:
            self.session_state[key] = value
        return value

    def button(self, _label, key=None, **_kwargs):
        return self.button_values.get(key, False)

    def columns(self, spec, **_kwargs):
        return [_FakeContext() for _ in spec]

    @contextmanager
    def container(self, **_kwargs):
        yield _FakeContext()

    def write(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def success(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None

    def rerun(self):
        return None


@pytest.fixture
def fake_streamlit(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    monkeypatch.setattr(streamlit_module, "rerun", fake_st.rerun, raising=False)
    return fake_st


@pytest.fixture
def patch_dashboard_db_init(monkeypatch):
    monkeypatch.setattr("components.design_modules.db_utils.init_db", lambda: None)


def test_save_load_round_trip_preserves_step1_to_step3_fields(monkeypatch):
    db_path = _restoration_stability_db_path("restoration_stability.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    session = DesignSession(
        step=3,
        gene_name="mCherry",
        original_seq="ATGGCCAAATTTGGGCCCTAA",
        host="E.coli BL21(DE3)",
        tag="His6-tag (C-term)",
        elements={
            "promoter_name": "Custom T7",
            "promoter_seq": "TAATACGACTCACTATAGGG",
            "rbs_name": "B0034",
            "rbs_seq": "AAAGAGGAGAAA",
            "terminator_name": "rrnB T1",
            "terminator_seq": "GCATCAAATAAAACGAAAGG",
        },
        optimized_seq="ATGGCGAAATTCGGTCCTTAA",
        codon_report={
            "success": True,
            "before": {"cai": 0.62},
            "after": {"cai": 0.91},
            "history": [{"position": 2, "from": "GCC", "to": "GCG"}],
        },
        frame={
            "success": True,
            "final_sequence": "TAATACGACTCACTATAGGGAAAGAGGAGAAAATGGCGAAATTCGGTCCTTAAGCATCAAATAAAACGAAAGG",
            "parts": [
                {"type": "promoter", "name": "Custom T7"},
                {"type": "RBS", "name": "B0034"},
                {"type": "CDS", "name": "mCherry"},
                {"type": "terminator", "name": "rrnB T1"},
            ],
            "features": [
                {"name": "Custom T7", "start": 1, "end": 20},
                {"name": "mCherry", "start": 33, "end": 56},
            ],
        },
    )

    saved_ok, saved_name = design_saver.save_wizard_design(session)
    assert saved_ok is True

    load_ok, restored = design_saver.load_wizard_design(saved_name)
    assert load_ok is True

    assert restored.gene_name == session.gene_name
    assert restored.original_seq == session.original_seq
    assert restored.host == session.host
    assert restored.tag == session.tag
    assert restored.elements == session.elements
    assert restored.optimized_seq == session.optimized_seq
    assert restored.codon_report == session.codon_report
    assert restored.frame.get("success") is True
    assert restored.frame.get("final_sequence") == session.frame["final_sequence"]
    assert restored.frame.get("parts") == session.frame["parts"]
    assert restored.frame.get("features") == session.frame["features"]


def test_dashboard_load_restores_active_context_from_loaded_session(
    monkeypatch,
    fake_streamlit,
    patch_dashboard_db_init,
):
    fake_streamlit.button_values["pw_load_btn"] = True
    fake_streamlit.session_state.update(
        {
            "wf_p2_host": "Old widget host",
            "wf_p2_prom": "Old widget promoter",
            "wf_p2_rbs": "Old widget rbs",
            "wf_p2_term": "Old widget terminator",
            SK.ACTIVE_HOST: "Old active host",
            SK.ACTIVE_SEQ: "OLDSEQ",
            SK.ACTIVE_FEATURES: [{"name": "old feature"}],
        }
    )

    loaded_session = DesignSession(
        step=1,
        gene_name="mCherry",
        original_seq="ATGGCCAAATTTGGGCCCTAA",
        optimized_seq="ATGOPTIMIZED",
        host="B. subtilis 168",
        frame={
            "success": True,
            "final_sequence": "ATGFRAMEFINAL",
            "features": [{"name": "loaded promoter", "start": 1, "end": 8}],
        },
    )

    monkeypatch.setattr(
        dashboard,
        "_get_projects_from_db",
        lambda *args, **kwargs: [
            {
                "Name": "Saved mCherry Design",
                "Gene": "mCherry",
                "Host": "B. subtilis 168",
                "Length (bp)": 99,
                "GC%": "50.0%",
                "Type": "Expression Design",
                "Saved": "2026-04-08 09:00",
                "_gene": "mCherry",
                "_host": "B. subtilis 168",
                "_cloning": "Gibson",
                "_step": 3,
                "_vector": "pET-28a",
                "_n_primers": 0,
                "_n_issues": 0,
            }
        ],
    )
    monkeypatch.setattr("services.design_saver.load_wizard_design", lambda name: (True, loaded_session))

    page_calls = []
    dashboard.render(page_calls.append)

    assert fake_streamlit.session_state["design_session"] is loaded_session
    assert fake_streamlit.session_state[SK.ACTIVE_HOST] == "B. subtilis 168"
    assert fake_streamlit.session_state[SK.ACTIVE_SEQ] == "ATGFRAMEFINAL"
    assert fake_streamlit.session_state[SK.ACTIVE_FEATURES] == [{"name": "loaded promoter", "start": 1, "end": 8}]
    assert fake_streamlit.session_state[SK.ACTIVE_NAME] == "Saved mCherry Design"
    assert fake_streamlit.session_state[SK.DASHBOARD_PROJECT] == "Saved mCherry Design"
    assert fake_streamlit.session_state["wf_p2_host"] == "Old widget host"
    assert page_calls == ["Expression Wizard"]


def test_load_wizard_design_restores_step2_override_sequences_from_project_history(monkeypatch):
    db_path = _restoration_stability_db_path("restoration_existing_payload.db")
    monkeypatch.setattr(design_saver, "DB_PATH", str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(CREATE_TABLES_SQL)
        conn.execute(
            "INSERT INTO project_history "
            "(project_name, version, chassis, design_data, created_at, creator, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "Saved Existing Design",
                1,
                "E.coli BL21(DE3)",
                '{'
                '"gene_name":"mCherry",'
                '"host":"E.coli BL21(DE3)",'
                '"tag":"His6-tag (C-term)",'
                '"promoter":"Custom T7",'
                '"rbs":"B0034",'
                '"terminator":"rrnB T1",'
                '"original_seq":"ATGGCCAAATTTGGGCCCTAA",'
                '"optimized_seq":"ATGGCGAAATTCGGTCCTTAA",'
                '"codon_report":{"success":true},'
                '"frame":{' 
                '"success":true,'
                '"final_sequence":"ATGFRAMEFINAL",'
                '"parts":[{"type":"promoter","name":"Custom T7"}],'
                '"features":[{"name":"Custom T7","start":1,"end":20}]'
                '},'
                '"method":"Expression Wizard",'
                '"step_reached":3,'
                '"saved_at":"2026-04-08T12:00:00"'
                '}',
                "2026-04-08 12:00:00",
                "Expression Wizard",
                "saved",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    load_ok, restored = design_saver.load_wizard_design("Saved Existing Design")
    assert load_ok is True
    assert restored.elements["promoter_name"] == "Custom T7"
    assert restored.elements["promoter_seq"] == ""
    assert restored.elements["rbs_name"] == "B0034"
    assert restored.elements["rbs_seq"] == ""
    assert restored.elements["terminator_name"] == "rrnB T1"
    assert restored.elements["terminator_seq"] == ""
