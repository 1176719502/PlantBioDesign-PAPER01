from __future__ import annotations

import os
import sys
from contextlib import contextmanager

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
import views.wizard_steps.step1_gene_input as step1_gene_input
import views.wizard_steps.step2_host_elements as step2_host_elements


LOADED_STEP1_SEQ = "ATGGCTGACAAACCGTTCGGTATCCAGTAA"
STALE_STEP1_SEQ = "ATG" + ("CCC" * 9) + "TAA"


class FakeStreamlit:
    def __init__(self):
        self.session_state: dict[str, object] = {}
        self.button_values: dict[str, bool] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info_messages: list[str] = []

    def markdown(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def write(self, *_args, **_kwargs):
        return None

    def code(self, *_args, **_kwargs):
        return None

    def success(self, *_args, **_kwargs):
        return None

    def warning(self, message, **_kwargs):
        self.warnings.append(message)

    def info(self, message, **_kwargs):
        self.info_messages.append(message)

    def error(self, message, **_kwargs):
        self.errors.append(message)

    def columns(self, spec, **_kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeContext() for _ in range(count)]

    @contextmanager
    def expander(self, *_args, **_kwargs):
        yield _FakeContext()

    @contextmanager
    def spinner(self, *_args, **_kwargs):
        yield _FakeContext()

    def radio(self, _label, options, key=None, **_kwargs):
        if key is not None and key in self.session_state and self.session_state[key] in options:
            value = self.session_state[key]
        else:
            value = options[0] if options else None
        if key is not None:
            self.session_state[key] = value
        return value

    def text_input(self, _label, value="", key=None, **_kwargs):
        if key is not None and key in self.session_state:
            current = self.session_state[key]
        else:
            current = value
        if key is not None:
            self.session_state[key] = current
        return current

    def text_area(self, _label, value="", key=None, **_kwargs):
        if key is not None and key in self.session_state:
            current = self.session_state[key]
        else:
            current = value
        if key is not None:
            self.session_state[key] = current
        return current

    def selectbox(self, _label, options, key=None, index=0, **_kwargs):
        if key is not None and key in self.session_state and self.session_state[key] in options:
            current = self.session_state[key]
        else:
            current = options[index] if options else None
        if key is not None:
            self.session_state[key] = current
        return current

    def button(self, _label, key=None, **_kwargs):
        return self.button_values.get(key, False)


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *_args, **_kwargs):
        return None


class FakeController:
    def __init__(self, ds: DesignSession):
        self.ds = ds
        self.save_calls = 0
        self.advance_calls = 0

    def get(self) -> DesignSession:
        return self.ds

    def save(self, ds: DesignSession) -> None:
        self.ds = ds
        self.save_calls += 1

    def advance(self) -> None:
        self.advance_calls += 1


@pytest.fixture
def fake_streamlit():
    return FakeStreamlit()


@pytest.fixture
def patch_step1(monkeypatch, fake_streamlit):
    monkeypatch.setattr(step1_gene_input, "st", fake_streamlit)
    monkeypatch.setattr(step1_gene_input, "_step_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step1_gene_input, "_section_label", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step1_gene_input, "_status_panel", lambda *_args, **_kwargs: None)
    return fake_streamlit


@pytest.fixture
def patch_step2(monkeypatch, fake_streamlit):
    monkeypatch.setattr(step2_host_elements, "st", fake_streamlit)
    monkeypatch.setattr(step2_host_elements, "_step_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step2_host_elements, "_section_label", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step2_host_elements, "_status_panel", lambda *_args, **_kwargs: None)
    return fake_streamlit


def test_step1_dashboard_load_ignores_stale_widget_state_on_confirm(patch_step1):
    fake_st = patch_step1
    fake_st.session_state.update(
        {
            "wf_p1_name": "Stale Name",
            "wf_p1_seq": STALE_STEP1_SEQ,
        }
    )
    fake_st.button_values["wf_p1_next"] = True

    loaded_session = DesignSession(
        step=1,
        gene_name="Loaded Gene",
        original_seq=LOADED_STEP1_SEQ,
    )
    ctrl = FakeController(loaded_session)

    step1_gene_input.page(ctrl)

    assert ctrl.ds.gene_name == "Loaded Gene"
    assert ctrl.ds.original_seq == LOADED_STEP1_SEQ
    assert fake_st.session_state["wf_p1_name"] == "Loaded Gene"
    assert fake_st.session_state["wf_p1_seq"] == LOADED_STEP1_SEQ
    assert ctrl.advance_calls == 1


def test_step2_dashboard_load_ignores_stale_widget_and_registry_override_state_on_confirm(
    patch_step2,
    monkeypatch,
):
    fake_st = patch_step2
    fake_st.session_state.update(
        {
            "wf_p2_host": "B. subtilis 168",
            "wf_p2_tag": "His6-tag (C-term)",
            "wf_p2_prom": "Stale promoter label",
            "wf_p2_rbs": "Stale rbs label",
            "wf_p2_term": "Stale terminator label",
            "wf_p2_prom_db": "Stale Promoter",
            "wf_p2_rbs_db": "Stale RBS",
            "wf_p2_term_db": "Stale Terminator",
        }
    )
    fake_st.button_values["wf_p2_next"] = True

    monkeypatch.setattr(
        step2_host_elements,
        "_db_parts_map_for_host",
        lambda _host, part_types: {
            "Promoter": [
                {"name": "Loaded Promoter", "sequence": "AAAACCCC", "length_bp": 8},
                {"name": "Stale Promoter", "sequence": "GGGGTTTT", "length_bp": 8},
            ],
            "RBS": [
                {"name": "Loaded RBS", "sequence": "AGGAGG", "length_bp": 6},
                {"name": "Stale RBS", "sequence": "CCCCCC", "length_bp": 6},
            ],
            "Terminator": [
                {"name": "Loaded Terminator", "sequence": "TTTTAAAA", "length_bp": 8},
                {"name": "Stale Terminator", "sequence": "AACCGGTT", "length_bp": 8},
            ],
        },
    )

    loaded_session = DesignSession(
        step=2,
        original_seq=LOADED_STEP1_SEQ,
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "Loaded Promoter",
            "promoter_seq": "AAAACCCC",
            "rbs_name": "Loaded RBS",
            "rbs_seq": "AGGAGG",
            "terminator_name": "Loaded Terminator",
            "terminator_seq": "TTTTAAAA",
        },
    )
    ctrl = FakeController(loaded_session)

    step2_host_elements.page(ctrl)

    assert ctrl.ds.host == "E.coli BL21(DE3)"
    assert ctrl.ds.tag == "No tag"
    assert ctrl.ds.elements == {
        "promoter_name": "Loaded Promoter",
        "promoter_seq": "AAAACCCC",
        "rbs_name": "Loaded RBS",
        "rbs_seq": "AGGAGG",
        "terminator_name": "Loaded Terminator",
        "terminator_seq": "TTTTAAAA",
    }
    assert fake_st.session_state["wf_p2_host"] == "E. coli BL21(DE3)"
    assert fake_st.session_state["wf_p2_tag"] == "No fusion tag"
    assert fake_st.session_state["wf_p2_tag_position"] == "Not recorded"
    assert fake_st.session_state["wf_p2_prom"] == "Loaded Promoter"
    assert fake_st.session_state["wf_p2_rbs"] == "Loaded RBS"
    assert fake_st.session_state["wf_p2_term"] == "Loaded Terminator"
    assert fake_st.session_state["wf_p2_prom_db"] == "Loaded Promoter"
    assert fake_st.session_state["wf_p2_rbs_db"] == "Loaded RBS"
    assert fake_st.session_state["wf_p2_term_db"] == "Loaded Terminator"
    assert ctrl.advance_calls == 1
