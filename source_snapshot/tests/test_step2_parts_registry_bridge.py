# -*- coding: utf-8 -*-
"""
Focused tests for Phase 2B-1 Parts Registry to Step 2 candidate bridge.
"""
from __future__ import annotations

import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd

from core.design_session import DesignSession
from core.session_keys import SK


class _Recorder:
    def __init__(self):
        self.texts: list[str] = []
        self.button_calls: list[dict[str, object]] = []
        self.expander_calls: list[dict[str, object]] = []
        self.button_map: dict[str, bool] = {}
        self.session_state: dict[str, object] = {}
        self.rerun_calls = 0

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, *args, **kwargs):
        self.recorder.add(*args)

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        return self.recorder.button_map.get(kwargs.get("key"), False)


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder
        self.session_state = recorder.session_state

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
        self.recorder.expander_calls.append({"label": label, **kwargs})
        self.recorder.add(label)
        return _Context()

    def divider(self):
        return None

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        return self.recorder.button_map.get(kwargs.get("key"), False)

    def code(self, body, **kwargs):
        self.recorder.add(body)

    def text_area(self, label, value="", **kwargs):
        self.recorder.add(label, value)
        return value

    def selectbox(self, label, options, index=0, **kwargs):
        self.recorder.add(label)
        return options[index]

    def text_input(self, label, value="", **kwargs):
        self.recorder.add(label)
        return value

    def rerun(self):
        self.recorder.rerun_calls += 1

    def toast(self, body, **kwargs):
        self.recorder.add(body)


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds
        self.save_calls = 0
        self.advance_calls = 0

    def get(self) -> DesignSession:
        return self._ds

    def save(self, ds: DesignSession) -> None:
        self._ds = ds
        self.save_calls += 1

    def advance(self) -> None:
        self.advance_calls += 1


def _base_ds() -> DesignSession:
    return DesignSession(
        step=2,
        gene_name="DemoGene",
        original_seq="ATG" + ("GCC" * 20) + "TAA",
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={},
        frame={"existing": True},
        optimized_seq="ATGGCC",
        primers=[{"name": "p1"}],
        validation_results=[{"status": "old"}],
    )


def _candidate(part_type: str = "Promoter", host: str = "E.coli", sequence: str = "ATGC") -> dict:
    return {
        "source": "parts_registry",
        "origin_page": "Parts Registry",
        "part_id": 1,
        "registry_id": 1,
        "part_type": part_type,
        "canonical_type": part_type,
        "name": f"Demo {part_type}",
        "sequence": sequence,
        "host_context": host,
        "organism": host,
        "notes": "Review note",
        "warnings": ["Review note"],
    }


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
            get_host_groups=lambda: {"Bacteria": ["E.coli BL21(DE3)"], "Plants": ["Rice (O. sativa)"]},
            get_host_rules=lambda host: {
                "tag_options": {"No tag": ""},
                "kingdom": "prokaryote" if "coli" in host.lower() else "plant_monocot",
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


def test_parts_registry_can_create_step2_candidate_payload():
    import views.Data as data

    row = pd.Series({
        "ID": 7,
        "Name": "T7 Promoter",
        "Type": "Promoter",
        "Organism": "E.coli",
        "Sequence": "TAATACGA",
        "Notes": "Use with T7 polymerase.",
        "Length (bp)": 8,
        "GC Content (%)": 25.0,
    })
    payload = data._build_step2_candidate_payload(row)

    assert payload["source"] == "parts_registry"
    assert payload["origin_page"] == "Parts Registry"
    assert payload["part_id"] == 7
    assert payload["registry_id"] == 7
    assert payload["part_type"] == "Promoter"
    assert payload["canonical_type"] == "Promoter"
    assert payload["name"] == "T7 Promoter"
    assert payload["sequence"] == "TAATACGA"
    assert payload["host_context"] == "E.coli"
    assert payload["notes"] == "Use with T7 polymerase."


def test_context_bridge_sends_payload_and_returns_wizard_to_step2(monkeypatch):
    import core.context_bridge as bridge

    recorder = _Recorder()
    ds = DesignSession(step=4, host="E.coli BL21(DE3)", tag="No tag", elements={"promoter_name": "Old"})
    recorder.session_state[SK.DESIGN_SESSION] = ds
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = _candidate("RBS")
    navigation_targets = []

    def fake_session_controller():
        return _FakeController(ds)

    monkeypatch.setitem(sys.modules, "streamlit", _FakeStreamlit(recorder))
    monkeypatch.setitem(sys.modules, "core.design_session", types.SimpleNamespace(SessionController=fake_session_controller))

    payload = _candidate("Promoter", sequence="")
    bridge.send_parts_step2_candidate(payload, navigation_targets.append)

    assert recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] == payload
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert ds.step == 2
    assert ds.host == "E.coli BL21(DE3)"
    assert ds.tag == "No tag"
    assert ds.elements == {"promoter_name": "Old"}
    assert navigation_targets == ["Expression Wizard"]


def test_unsupported_types_cannot_send_enabled_candidate():
    import views.Data as data

    assert data._is_step2_candidate_type("Promoter") is True
    assert data._is_step2_candidate_type("RBS") is True
    assert data._is_step2_candidate_type("Terminator") is True
    assert data._is_step2_candidate_type("CDS") is False
    assert data._is_step2_candidate_type("Vector") is False
    assert data._is_step2_candidate_type("unknown") is False


def test_candidate_visibility_does_not_write_formal_or_downstream_fields(monkeypatch):
    ds = _base_ds()
    original = (ds.host, ds.tag, dict(ds.elements), dict(ds.frame), ds.optimized_seq, list(ds.primers), list(ds.validation_results))
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate()
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert "Parts Registry candidate" in recorder.joined()
    assert "Candidate review status" in recorder.joined()
    assert (ds.host, ds.tag, dict(ds.elements), dict(ds.frame), ds.optimized_seq, list(ds.primers), list(ds.validation_results)) == original
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_step2_renders_component_library_context_without_writing_state(monkeypatch):
    ds = _base_ds()
    original = (ds.host, ds.tag, dict(ds.elements), dict(ds.frame), ds.optimized_seq, list(ds.primers), list(ds.validation_results))
    recorder = _Recorder()
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    rendered = recorder.joined()
    expander_labels = [call["label"] for call in recorder.expander_calls]
    assert "Component Library context" in rendered
    assert "Compact documentation summary" in rendered
    assert "Related records found" in rendered
    assert "Rows needing source/provenance review" in rendered
    assert "Rows needing manual follow-up" in rendered
    assert "Rows with incomplete sequence metadata" in rendered
    assert "Additional context records are hidden by default to keep Step 2 readable." in rendered
    assert "Review all linked component context records" in expander_labels
    assert any(call["label"] == "Review all linked component context records" and call.get("expanded") is False for call in recorder.expander_calls)
    assert "Promoter" in rendered
    assert "RBS / Shine-Dalgarno" in rendered
    assert "Terminator" in rendered
    assert "recorded context" in rendered
    assert "source/provenance review" in rendered
    assert "manual follow-up" in rendered
    assert "not a biological recommendation" in rendered
    assert (ds.host, ds.tag, dict(ds.elements), dict(ds.frame), ds.optimized_seq, list(ds.primers), list(ds.validation_results)) == original
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_step2_component_library_context_empty_state_is_safe(monkeypatch):
    recorder = _Recorder()
    step2 = _install_step2(monkeypatch, recorder)
    monkeypatch.setattr(
        step2,
        "_render_component_library_context",
        lambda host, tag, rules, elements: (
            recorder.add("Component Library context"),
            recorder.add("No Component Library context is recorded for the current Step 2 review surface."),
            recorder.add("Manual follow-up is required in the existing Component Library or review surfaces."),
            recorder.add("not a biological recommendation"),
        ),
    )

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined()
    assert "No Component Library context is recorded" in rendered
    assert "Manual follow-up" in rendered
    assert "not a biological recommendation" in rendered


def test_step2_component_library_context_copy_avoids_recommendation_claims(monkeypatch):
    recorder = _Recorder()
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined().lower()
    for forbidden in [
        "best host",
        "best promoter",
        "high expression",
        "optimized pathway",
        "validated construct",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "yield prediction",
    ]:
        assert forbidden not in rendered


def test_use_candidate_requires_explicit_click(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate()
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert "Use Candidate Record" in [call["label"] for call in recorder.button_calls]


def test_use_candidate_does_not_auto_confirm_or_advance(monkeypatch):
    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate()
    recorder.button_map["wf_p2_use_parts_candidate"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE]["name"] == "Demo Promoter"
    assert ds.elements == {}
    assert ds.frame == {"existing": True}
    assert ds.optimized_seq == "ATGGCC"
    assert ds.primers == [{"name": "p1"}]
    assert ds.validation_results == [{"status": "old"}]
    assert ds.step == 2
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_dismiss_clears_bridge_and_selected_candidate_state(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate()
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = _candidate()
    recorder.button_map["wf_p2_dismiss_parts_candidate"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ds = _base_ds()

    step2.page(_FakeController(ds))

    assert SK.PARTS_STEP2_CANDIDATE_BRIDGE not in recorder.session_state
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert ds.elements == {}
    assert recorder.rerun_calls == 1


def test_unknown_host_candidate_blocks_selection(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate(host="")
    recorder.button_map["wf_p2_use_parts_candidate"] = True
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined()
    assert "Host context unavailable" in rendered
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state


def test_hard_host_mismatch_blocks_selection(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate(host="Rice")
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined()
    assert "Host context differs" in rendered
    use_calls = [call for call in recorder.button_calls if call["label"] == "Use Candidate Record"]
    assert use_calls == []
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state


def test_type_mismatch_blocks_selection(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate(part_type="CDS")
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined()
    assert "Unsupported type" in rendered
    use_calls = [call for call in recorder.button_calls if call["label"] == "Use Candidate"]
    assert use_calls == []
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state


def test_missing_sequence_blocks_selection(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate(sequence="")
    recorder.button_map["wf_p2_use_parts_candidate"] = True
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined()
    assert "Missing sequence" in rendered
    use_calls = [call for call in recorder.button_calls if call["label"] == "Use Candidate Record"]
    assert use_calls == []
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state


def test_confirm_merges_selected_candidate_only_at_confirm_time(monkeypatch):
    ds = _base_ds()
    candidate = _candidate(part_type="RBS", sequence="GGAGGA")
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = candidate
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = candidate
    recorder.button_map["wf_p2_next"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert ds.host == "E.coli BL21(DE3)"
    assert ds.tag == "No tag"
    assert ds.elements["promoter_name"] == ""
    assert ds.elements["promoter_seq"] == ""
    assert ds.elements["rbs_name"] == "Demo RBS"
    assert ds.elements["rbs_seq"] == "GGAGGA"
    assert ds.elements["terminator_name"] == ""
    assert ds.elements["terminator_seq"] == ""
    assert SK.PARTS_STEP2_CANDIDATE_BRIDGE not in recorder.session_state
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert ctrl.save_calls >= 1
    assert ctrl.advance_calls == 1


def test_confirm_blocks_stale_selected_candidate_and_clears_selected_state(monkeypatch):
    ds = _base_ds()
    bridge_candidate = _candidate(part_type="Promoter", sequence="AAAA")
    stale_candidate = _candidate(part_type="Terminator", sequence="TTTT")
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = bridge_candidate
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = stale_candidate
    recorder.button_map["wf_p2_next"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert "selected Parts Registry candidate is stale" in recorder.joined()
    assert recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] == bridge_candidate
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert ds.elements == {}
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_confirm_blocks_host_mismatched_selected_candidate_and_clears_selected_state(monkeypatch):
    ds = _base_ds()
    mismatched_candidate = _candidate(part_type="Promoter", host="Rice", sequence="AAAA")
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = mismatched_candidate
    recorder.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = mismatched_candidate
    recorder.button_map["wf_p2_next"] = True
    step2 = _install_step2(monkeypatch, recorder)
    ctrl = _FakeController(ds)

    step2.page(ctrl)

    assert "Host context differs" in recorder.joined()
    assert recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] == mismatched_candidate
    assert SK.PARTS_STEP2_SELECTED_CANDIDATE not in recorder.session_state
    assert ds.elements == {}
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_step2_candidate_copy_avoids_authority_style_host_compatibility_wording(monkeypatch):
    recorder = _Recorder()
    recorder.session_state[SK.PARTS_STEP2_CANDIDATE_BRIDGE] = _candidate()
    step2 = _install_step2(monkeypatch, recorder)

    step2.page(_FakeController(_base_ds()))

    rendered = recorder.joined().lower()
    assert "candidate review status" in rendered
    assert "documented host context" in rendered
    assert "candidate available for review" in rendered
    assert "compatible candidate" not in rendered
    assert "compatibility status" not in rendered
    assert "candidate host" not in rendered
    assert "host is ready" not in rendered
