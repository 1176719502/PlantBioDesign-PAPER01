from __future__ import annotations

import os
import sys
from contextlib import contextmanager

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from core.design_session import DesignSession
from core.session_keys import SK
from services.pathway_wizard_context import PATHWAY_WIZARD_CONTEXT_KEY
import views.Dashboard as dashboard


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
        self.success_messages = []
        self.error_messages = []
        self.info_messages = []
        self.caption_messages = []
        self.markdown_calls = []
        self.dataframes = []
        self.rerun_calls = 0
        self.column_config = _FakeColumnConfig()

    def markdown(self, body, **_kwargs):
        self.markdown_calls.append(body)

    def text_input(self, _label, key=None, placeholder=None, **_kwargs):
        value = self.text_input_values.get(key, self.session_state.get(key, ""))
        if key is not None:
            self.session_state[key] = value
        return value

    def selectbox(self, _label, options, key=None, index=0, **_kwargs):
        if key in self.selectbox_values:
            value = self.selectbox_values[key]
        elif key is not None and key in self.session_state and self.session_state[key] in options:
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

    def caption(self, message, **_kwargs):
        self.caption_messages.append(message)

    def info(self, message, **_kwargs):
        self.info_messages.append(message)

    def dataframe(self, data, **_kwargs):
        self.dataframes.append(data)

    def success(self, message, **_kwargs):
        self.success_messages.append(message)

    def error(self, message, **_kwargs):
        self.error_messages.append(message)

    def rerun(self):
        self.rerun_calls += 1


@pytest.fixture
def fake_streamlit(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(dashboard, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    monkeypatch.setattr(streamlit_module, "rerun", fake_st.rerun, raising=False)
    return fake_st


@pytest.fixture
def change_page_recorder():
    calls = []

    def _change_page(page_name: str) -> None:
        calls.append(page_name)

    return calls, _change_page


@pytest.fixture
def sample_project_rows():
    return [
        {
            "Name": "Saved Design A",
            "Gene": "GFP",
            "Host": "E.coli BL21(DE3)",
            "Length (bp)": 1200,
            "GC%": "51.0%",
            "Type": "Expression Design",
            "Saved": "2026-04-08 09:00",
            "_gene": "GFP",
            "_host": "E.coli BL21(DE3)",
            "_cloning": "Gibson",
            "_step": 6,
            "_vector": "pET-28a",
            "_n_primers": 2,
            "_n_issues": 0,
        }
    ]


@pytest.fixture
def patch_dashboard_db_init(monkeypatch):
    monkeypatch.setattr("components.design_modules.db_utils.init_db", lambda: None)


def _render_dashboard(monkeypatch, fake_streamlit, change_page, project_rows):
    monkeypatch.setattr(dashboard, "_get_projects_from_db", lambda *args, **kwargs: list(project_rows))
    dashboard.render(change_page)


def test_load_design_restores_session_and_navigates_to_expression_wizard(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    page_calls, change_page = change_page_recorder
    fake_streamlit.button_values["pw_load_btn"] = True

    loaded_session = DesignSession(
        step=1,
        gene_name="GFP",
        original_seq="ATGAAA",
        optimized_seq="ATGCCC",
        host="E.coli BL21(DE3)",
        frame={
            "final_sequence": "ATGTTT",
            "features": [{"name": "promoter", "start": 1, "end": 3}],
            "success": True,
        },
    )
    monkeypatch.setattr("services.design_saver.load_wizard_design", lambda name: (True, loaded_session))

    _render_dashboard(monkeypatch, fake_streamlit, change_page, sample_project_rows)

    assert fake_streamlit.session_state["design_session"] is loaded_session
    assert fake_streamlit.session_state[SK.ACTIVE_HOST] == "E.coli BL21(DE3)"
    assert fake_streamlit.session_state[SK.ACTIVE_SEQ] == "ATGTTT"
    assert fake_streamlit.session_state[SK.ACTIVE_FEATURES] == [{"name": "promoter", "start": 1, "end": 3}]
    assert fake_streamlit.session_state[SK.ACTIVE_NAME] == "Saved Design A"
    assert fake_streamlit.session_state[SK.DASHBOARD_PROJECT] == "Saved Design A"
    assert page_calls == ["Expression Wizard"]


def test_dashboard_load_clears_stale_pathway_context(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    page_calls, change_page = change_page_recorder
    fake_streamlit.button_values["pw_load_btn"] = True
    fake_streamlit.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }
    loaded_session = DesignSession(
        step=1,
        gene_name="GFP",
        original_seq="ATGAAA",
        optimized_seq="ATGCCC",
        host="E.coli BL21(DE3)",
        frame={"final_sequence": "ATGTTT", "features": [], "success": True},
    )
    monkeypatch.setattr("services.design_saver.load_wizard_design", lambda name: (True, loaded_session))

    _render_dashboard(monkeypatch, fake_streamlit, change_page, sample_project_rows)

    assert PATHWAY_WIZARD_CONTEXT_KEY not in fake_streamlit.session_state
    assert page_calls == ["Expression Wizard"]


def test_dashboard_new_clears_stale_pathway_context(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    page_calls, change_page = change_page_recorder
    fake_streamlit.button_values["pw_new_btn"] = True
    fake_streamlit.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 1,
        "step_id": 2,
    }

    _render_dashboard(monkeypatch, fake_streamlit, change_page, sample_project_rows)

    assert PATHWAY_WIZARD_CONTEXT_KEY not in fake_streamlit.session_state
    assert page_calls == ["Expression Wizard"]


def test_load_design_prefers_frame_final_sequence_for_active_seq(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    page_calls, change_page = change_page_recorder
    fake_streamlit.button_values["pw_load_btn"] = True

    loaded_session = DesignSession(
        step=1,
        gene_name="GFP",
        original_seq="ATGORIGINAL",
        optimized_seq="ATGOPTIMIZED",
        host="E.coli BL21(DE3)",
        frame={
            "final_sequence": "ATGFINAL",
            "features": [],
            "success": True,
        },
    )
    monkeypatch.setattr("services.design_saver.load_wizard_design", lambda name: (True, loaded_session))

    _render_dashboard(monkeypatch, fake_streamlit, change_page, sample_project_rows)

    assert fake_streamlit.session_state[SK.ACTIVE_SEQ] == "ATGFINAL"
    assert fake_streamlit.session_state["design_session"] is loaded_session
    assert page_calls == ["Expression Wizard"]


def test_new_design_clears_previous_design_session_and_active_context(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    page_calls, change_page = change_page_recorder
    fake_streamlit.button_values["pw_new_btn"] = True
    fake_streamlit.session_state.update(
        {
            "design_session": DesignSession(gene_name="Legacy"),
            SK.ACTIVE_SEQ: "ATGOLD",
            SK.ACTIVE_HOST: "Legacy Host",
            SK.ACTIVE_FEATURES: [{"name": "legacy"}],
            SK.ACTIVE_NAME: "Legacy Project",
            SK.DASHBOARD_PROJECT: "Saved Design A",
        }
    )

    _render_dashboard(monkeypatch, fake_streamlit, change_page, sample_project_rows)

    assert "design_session" not in fake_streamlit.session_state
    assert SK.ACTIVE_SEQ not in fake_streamlit.session_state
    assert SK.ACTIVE_HOST not in fake_streamlit.session_state
    assert SK.ACTIVE_FEATURES not in fake_streamlit.session_state
    assert SK.ACTIVE_NAME not in fake_streamlit.session_state
    assert SK.DASHBOARD_PROJECT not in fake_streamlit.session_state
    assert page_calls == ["Expression Wizard"]


def test_delete_design_removes_it_from_dashboard_source_on_next_render(
    monkeypatch,
    fake_streamlit,
    change_page_recorder,
    sample_project_rows,
    patch_dashboard_db_init,
):
    _page_calls, change_page = change_page_recorder
    project_rows = list(sample_project_rows)
    deleted_names = []

    def _delete_design(name: str):
        deleted_names.append(name)
        project_rows[:] = [row for row in project_rows if row["Name"] != name]
        return True, name

    monkeypatch.setattr("services.design_saver.delete_wizard_design", _delete_design)

    fake_streamlit.button_values = {"pw_del_btn": True}
    _render_dashboard(monkeypatch, fake_streamlit, change_page, project_rows)

    assert fake_streamlit.session_state["pw_confirm_delete"] == "Saved Design A"
    assert fake_streamlit.rerun_calls == 1

    fake_streamlit.button_values = {"pw_del_confirm_btn": True}
    _render_dashboard(monkeypatch, fake_streamlit, change_page, project_rows)

    assert deleted_names == ["Saved Design A"]
    assert project_rows == []
    assert "pw_confirm_delete" not in fake_streamlit.session_state
    assert fake_streamlit.rerun_calls == 2

    fake_streamlit.button_values = {}
    _render_dashboard(monkeypatch, fake_streamlit, change_page, project_rows)

    assert any("No saved designs yet" in body for body in fake_streamlit.markdown_calls)
