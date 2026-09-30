# -*- coding: utf-8 -*-
"""
Focused tests for Phase 2B-1 Step 2 candidate confirm-time application.
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

from tests.test_step2_parts_registry_bridge import _FakeController, _FakeStreamlit, _Recorder, _candidate


def _base_ds() -> DesignSession:
    return DesignSession(
        step=2,
        gene_name="DemoGene",
        original_seq="ATG" + ("GCC" * 20) + "TAA",
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "Old Promoter",
            "promoter_seq": "OLDP",
            "rbs_name": "Old RBS",
            "rbs_seq": "OLDR",
            "terminator_name": "Old Terminator",
            "terminator_seq": "OLDT",
        },
        frame={},
        optimized_seq="",
        primers=[],
        validation_results=[],
    )


def _install_step2(monkeypatch, recorder: _Recorder):
    import views.wizard_steps.step2_host_elements as step2

    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(step2, "st", fake_st)
    monkeypatch.setattr(step2, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step2, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step2, "_status_panel", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step2, "_db_parts_map_for_host", lambda host, part_types: {})
    monkeypatch.setitem(
        sys.modules,
        "core.expression_frame_builder",
        types.SimpleNamespace(
            get_host_groups=lambda: {"Bacteria": ["E.coli BL21(DE3)"]},
            get_host_rules=lambda host: {
                "tag_options": {"No tag": ""},
                "kingdom": "prokaryote",
                "promoter": "Default Promoter",
                "promoter_seq": "AAA",
                "promoter_note": "Default promoter note",
                "rbs": "Default RBS",
                "rbs_seq": "GGG",
                "rbs_note": "Default rbs note",
                "terminator": "Default Terminator",
                "terminator_seq": "TTT",
                "vector_suggestion": "Default Vector",
                "gc_optimal": (40, 60),
            },
        ),
    )
    return step2


def _confirm_with_candidate(monkeypatch, candidate: dict):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = candidate
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = candidate
    recorder.button_map["wf_p2_next"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)
    return ds, ctrl, recorder


def test_selected_promoter_only_overrides_promoter_on_confirm(monkeypatch):
    ds, ctrl, recorder = _confirm_with_candidate(monkeypatch, _candidate("Promoter", sequence="PROMSEQ"))

    assert ctrl.save_calls == 1
    assert ctrl.advance_calls == 1
    assert ds.elements["promoter_name"] == "Demo Promoter"
    assert ds.elements["promoter_seq"] == "PROMSEQ"
    assert ds.elements["rbs_name"] == "Old RBS"
    assert ds.elements["rbs_seq"] == ""
    assert ds.elements["terminator_name"] == "Old Terminator"
    assert ds.elements["terminator_seq"] == ""
    assert SK.PARTS_STEP2_CANDIDATE_BRIDGE not in recorder.session_state
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state


def test_selected_rbs_only_overrides_rbs_on_confirm(monkeypatch):
    ds, ctrl, _ = _confirm_with_candidate(monkeypatch, _candidate("RBS", sequence="RBSSEQ"))

    assert ctrl.save_calls == 1
    assert ctrl.advance_calls == 1
    assert ds.elements["promoter_name"] == "Old Promoter"
    assert ds.elements["promoter_seq"] == ""
    assert ds.elements["rbs_name"] == "Demo RBS"
    assert ds.elements["rbs_seq"] == "RBSSEQ"
    assert ds.elements["terminator_name"] == "Old Terminator"
    assert ds.elements["terminator_seq"] == ""


def test_selected_terminator_only_overrides_terminator_on_confirm(monkeypatch):
    ds, ctrl, _ = _confirm_with_candidate(monkeypatch, _candidate("Terminator", sequence="TERMSEQ"))

    assert ctrl.save_calls == 1
    assert ctrl.advance_calls == 1
    assert ds.elements["promoter_name"] == "Old Promoter"
    assert ds.elements["promoter_seq"] == ""
    assert ds.elements["rbs_name"] == "Old RBS"
    assert ds.elements["rbs_seq"] == ""
    assert ds.elements["terminator_name"] == "Demo Terminator"
    assert ds.elements["terminator_seq"] == "TERMSEQ"


def test_confirm_writes_selected_candidate_only_after_confirm(monkeypatch):
    ds = _base_ds()
    candidate = _candidate("Promoter", sequence="PROMSEQ")
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = candidate
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = candidate
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0
    assert ds.elements["promoter_name"] == "Old Promoter"
    assert ds.elements["promoter_seq"] == "OLDP"

    recorder.button_map["wf_p2_next"] = True
    step2.page(ctrl)

    assert ctrl.save_calls == 1
    assert ctrl.advance_calls == 1
    assert ds.elements["promoter_name"] == "Demo Promoter"
    assert ds.elements["promoter_seq"] == "PROMSEQ"


def test_step3_builder_can_receive_confirmed_regulatory_element(monkeypatch):
    ds, _, _ = _confirm_with_candidate(monkeypatch, _candidate("Promoter", sequence="PROMSEQ"))

    calls = []

    def fake_build_expression_frame(**kwargs):
        calls.append(kwargs)
        return {"success": True, "final_sequence": kwargs["promoter_seq"] + kwargs["gene_seq"]}

    fake_build_expression_frame(
        gene_seq=ds.original_seq,
        promoter_seq=ds.elements["promoter_seq"],
        rbs_seq=ds.elements["rbs_seq"],
        terminator_seq=ds.elements["terminator_seq"],
    )

    assert calls[0]["promoter_seq"] == "PROMSEQ"
    assert calls[0]["gene_seq"] == ds.original_seq
