# -*- coding: utf-8 -*-
"""
Focused regression tests for Phase 2A-2 explicit Step 3 candidate application.
"""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from core.session_keys import SK


class _Recorder:
    def __init__(self):
        self.texts: list[str] = []
        self.button_calls: list[dict[str, object]] = []
        self.button_map: dict[str, bool] = {}
        self.session_state: dict[str, object] = {}
        self.rerun_calls = 0
        self.optimize_calls: list[dict[str, object]] = []
        self.build_calls: list[dict[str, object]] = []

    def add(self, *values) -> None:
        for value in values:
            if value is not None:
                self.texts.append(str(value))

    def joined(self) -> str:
        return "\n".join(self.texts)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeColumn:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, *args, **kwargs):
        self.recorder.add(*args)

    def info(self, body, **kwargs):
        self.recorder.add(body)


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder
        self.session_state = recorder.session_state

    def spinner(self, body, **kwargs):
        self.recorder.add(body)
        return _Context()

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def caption(self, body, **kwargs):
        self.recorder.add(body)

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def warning(self, body, **kwargs):
        self.recorder.add(body)

    def success(self, body, **kwargs):
        self.recorder.add(body)

    def error(self, body, **kwargs):
        self.recorder.add(body)

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn(self.recorder) for _ in range(count)]

    def expander(self, label, **kwargs):
        self.recorder.add(label)
        return _Context()

    def divider(self):
        return None

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        key = kwargs.get("key")
        return self.recorder.button_map.get(key, False)

    def code(self, body, **kwargs):
        self.recorder.add(body)

    def rerun(self):
        self.recorder.rerun_calls += 1


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds
        self.save_calls = 0

    def get(self) -> DesignSession:
        return self._ds

    def save(self, ds: DesignSession) -> None:
        self._ds = ds
        self.save_calls += 1

    def advance(self) -> None:
        return None


def _base_ds() -> DesignSession:
    return DesignSession(
        step=3,
        gene_name="DemoGene",
        original_seq="ATG" + ("GCC" * 20) + "TAA",
        optimized_seq="",
        host="E.coli BL21(DE3)",
        tag="No tag",
        frame={},
        codon_report={},
    )


def _candidate_payload(host: str = "E.coli") -> dict:
    return {
        "source": "codon_optimizer",
        "candidate_seq": "ATG" + ("GCT" * 20) + "TAA",
        "input_sequence": "ATG" + ("GCC" * 20) + "TAA",
        "optimizer_host": host,
        "codon_report": {
            "success": True,
            "before": {"cai": 0.6},
            "after": {"cai": 0.8},
            "warnings": ["Example warning"],
            "history": [{"from": "GCC", "to": "GCT"}],
        },
        "sequence_length": 66,
        "gc_percent": 51.5,
        "cai_before": 0.6,
        "cai_after": 0.8,
        "warnings": ["Example warning"],
        "protein_preserved": True,
        "created_at": "2026-05-12T10:00:00",
        "origin_page": "CodonOptimizer",
        "status": "available",
    }


def _install_fakes(monkeypatch, recorder: _Recorder):
    import views.wizard_steps.step3_expression_frame as step3

    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    def fake_optimize_cds_sequence(**kwargs):
        recorder.optimize_calls.append(kwargs)
        return {
            "success": True,
            "optimized_sequence": "ATG" + ("GCA" * 20) + "TAA",
            "before": {"cai": 0.5},
            "after": {"cai": 0.7},
            "warnings": [],
            "history": [],
        }

    def fake_build_expression_frame(**kwargs):
        recorder.build_calls.append(kwargs)
        return {
            "success": True,
            "final_sequence": "PROM" + kwargs["gene_seq"] + "TERM",
            "total_length": len(kwargs["gene_seq"]) + 8,
            "gc_content": 50.0,
            "parts": [],
        }

    monkeypatch.setitem(
        sys.modules,
        "core.codon_optimizer",
        types.SimpleNamespace(optimize_cds_sequence=fake_optimize_cds_sequence),
    )
    monkeypatch.setattr(step3, "build_expression_frame", fake_build_expression_frame, raising=False)
    monkeypatch.setitem(
        sys.modules,
        "core.expression_frame_builder",
        types.SimpleNamespace(
            build_expression_frame=fake_build_expression_frame,
            build_step3_fidelity_summary=lambda **kwargs: {},
            get_host_rules=lambda host: {"codon_table_key": "E.coli"},
        ),
    )
    return step3


def test_compatible_candidate_can_be_selected(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    recorder.button_map["wf_p3_use_candidate_for_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(_base_ds()))

    assert SK.CODON_STEP3_SELECTED_CANDIDATE in recorder.session_state
    assert "External draft selected for next Step 3 expression-frame preview" in recorder.joined()


def test_selection_does_not_write_formal_step3_fields(monkeypatch):
    ds = _base_ds()
    original_seq = ds.original_seq
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    recorder.button_map["wf_p3_use_candidate_for_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    assert ds.original_seq == original_seq
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}
    assert recorder.optimize_calls == []
    assert recorder.build_calls == []


def test_selected_candidate_requires_explicit_main_build_button(monkeypatch):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = _candidate_payload()
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}
    assert recorder.optimize_calls == []
    assert recorder.build_calls == []


def test_main_build_using_selected_candidate_skips_optimizer_and_writes_fields(monkeypatch):
    ds = _base_ds()
    original_seq = ds.original_seq
    candidate = _candidate_payload()
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = candidate
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = candidate
    recorder.button_map["wf_p3_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    assert recorder.optimize_calls == []
    assert recorder.build_calls[0]["gene_seq"] == candidate["candidate_seq"]
    assert ds.original_seq == original_seq
    assert ds.optimized_seq == candidate["candidate_seq"]
    assert ds.codon_report["source"] == "codon_optimizer_candidate"
    assert ds.codon_report["step3_candidate_applied"] is True
    assert ds.codon_report["origin_page"] == "CodonOptimizer"
    assert ds.codon_report["before"] == {"cai": 0.6}
    assert ds.codon_report["after"] == {"cai": 0.8}
    assert ds.frame["success"] is True
    assert ds.frame_context_signature
    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state
    assert SK.CODON_STEP3_CANDIDATE_BRIDGE not in recorder.session_state


def test_mismatch_candidate_cannot_be_selected(monkeypatch):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload(host="Yeast")
    recorder.button_map["wf_p3_use_candidate_for_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    labels = [call["label"] for call in recorder.button_calls]
    assert "Use external draft for expression-frame preview" not in labels
    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state


def test_dismiss_clears_candidate_and_selected_state(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = _candidate_payload()
    recorder.button_map["wf_p3_dismiss_candidate_mismatch"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(_base_ds()))

    assert SK.CODON_STEP3_CANDIDATE_BRIDGE not in recorder.session_state
    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state


def test_new_candidate_handoff_clears_stale_selected_candidate(monkeypatch):
    import core.context_bridge as context_bridge

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = _candidate_payload(host="Yeast")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    context_bridge.send_codon_step3_candidate(_candidate_payload())

    assert SK.CODON_STEP3_CANDIDATE_BRIDGE in recorder.session_state
    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state


def test_stale_selected_candidate_host_mismatch_at_build_time_is_blocked(monkeypatch):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = _candidate_payload(host="Yeast")
    recorder.button_map["wf_p3_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}
    assert recorder.optimize_calls == []
    assert recorder.build_calls == []
    assert "Selected external draft host no longer matches" in recorder.joined()


def test_legacy_step3_build_without_selected_candidate_still_works(monkeypatch):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.button_map["wf_p3_build"] = True
    step3 = _install_fakes(monkeypatch, recorder)

    step3.page(_FakeController(ds))

    assert len(recorder.optimize_calls) == 1
    assert recorder.optimize_calls[0]["sequence"] == ds.original_seq
    assert len(recorder.build_calls) == 1
    assert recorder.build_calls[0]["gene_seq"] == "ATG" + ("GCA" * 20) + "TAA"
    assert ds.optimized_seq == "ATG" + ("GCA" * 20) + "TAA"
    assert ds.codon_report["success"] is True
    assert ds.frame["success"] is True
