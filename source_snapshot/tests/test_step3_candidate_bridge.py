# -*- coding: utf-8 -*-
"""
Focused regression tests for Phase 2A-1 Step 3 candidate bridge behavior.
"""
from __future__ import annotations

import os
import sys

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

    def add(self, *values) -> None:
        for value in values:
            if value is None:
                continue
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
        "codon_report": {"success": True, "before": {"cai": 0.6}, "after": {"cai": 0.8}},
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


def test_candidate_panel_appears_only_when_bridge_payload_exists(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    ds = _base_ds()

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(ds))
    assert "External review draft available" not in recorder.joined()

    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(_base_ds()))
    assert "External review draft available" in recorder.joined()
    assert "Step 3 itself does not generate synonymous recoding candidates in this batch." in recorder.joined()


def test_candidate_draft_preview_is_not_generated_before_explicit_action(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    ds = _base_ds()

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(ds))

    rendered = recorder.joined()
    labels = [call["label"] for call in recorder.button_calls]
    assert "Preview computational codon candidate draft" in labels
    assert "Codon candidate draft review" not in rendered
    assert "Review codon candidate draft sequence" not in rendered
    assert SK.CODON_STEP3_CANDIDATE_DRAFT_PREVIEW not in recorder.session_state
    assert ds.original_seq
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}


def test_candidate_draft_preview_after_explicit_action_shows_safe_comparison(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    recorder.button_map["wf_p3_generate_candidate_draft"] = True
    fake_st = _FakeStreamlit(recorder)
    ds = _base_ds()

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(ds))

    rendered = recorder.joined()
    labels = [call["label"] for call in recorder.button_calls]
    assert "Preview computational codon candidate draft" in labels
    assert "Generating codon candidate draft for documentation review..." in rendered
    assert "Codon candidate draft review" in rendered
    assert "computational synonymous recoding draft for documentation review only" in rendered
    assert "not a biological recommendation" in rendered
    assert "not experimentally validated" in rendered
    assert "not optimization proof" in rendered
    assert "not build-ready" in rendered
    for metric_label in [
        "Original length",
        "Candidate length",
        "Original GC%",
        "Candidate GC%",
        "Original rare codon count",
        "Candidate rare codon count",
        "Original rare codon clusters",
        "Candidate rare codon clusters",
        "Translation preserved status",
        "Validation/review flags",
    ]:
        assert metric_label in rendered
    assert "Review codon candidate draft sequence" in rendered
    assert SK.CODON_STEP3_CANDIDATE_DRAFT_PREVIEW in recorder.session_state
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}
    assert ds.step == 3


def test_invalid_candidate_draft_input_shows_review_flags_without_crashing(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    recorder.button_map["wf_p3_generate_candidate_draft"] = True
    fake_st = _FakeStreamlit(recorder)
    ds = _base_ds()
    ds.original_seq = "ATGNNTAA"

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Codon candidate draft was not created." in rendered
    assert "Review flags/messages: CDS contains invalid or ambiguous bases." in rendered
    assert "invalid_or_ambiguous_bases_detected" in rendered
    assert "Review codon candidate draft sequence" not in rendered
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}


def test_host_mismatch_blocks_candidate_use(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload(host="Yeast")
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(_base_ds()))
    rendered = recorder.joined()
    assert "External draft host mismatch" in rendered
    assert "This external draft cannot be used for the current Step 2 host context." in rendered
    labels = [call["label"] for call in recorder.button_calls]
    assert "Dismiss external draft" in labels
    assert "Use external draft for expression-frame preview" not in labels


def test_dismiss_candidate_clears_transient_payload(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload(host="Yeast")
    recorder.session_state[SK.CODON_STEP3_SELECTED_CANDIDATE] = _candidate_payload()
    recorder.button_map["wf_p3_dismiss_candidate_mismatch"] = True
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: None)

    step3.page(_FakeController(_base_ds()))
    assert SK.CODON_STEP3_CANDIDATE_BRIDGE not in recorder.session_state
    assert SK.CODON_STEP3_SELECTED_CANDIDATE not in recorder.session_state
    assert recorder.rerun_calls == 1


def test_candidate_visibility_does_not_modify_formal_step3_fields(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    ds = _base_ds()
    original_seq = ds.original_seq
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    fake_st = _FakeStreamlit(recorder)
    ctrl = _FakeController(ds)

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: None)

    step3.page(ctrl)
    assert ds.original_seq == original_seq
    assert ds.optimized_seq == ""
    assert ds.codon_report == {}
    assert ds.frame == {}


def test_candidate_does_not_auto_advance_workflow(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    ds = _base_ds()
    recorder = _Recorder()
    recorder.session_state[SK.CODON_STEP3_CANDIDATE_BRIDGE] = _candidate_payload()
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: None)

    step3.page(_FakeController(ds))
    assert ds.step == 3
    assert recorder.rerun_calls == 0


def test_legacy_step3_flow_without_candidate_still_works(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))

    step3.page(_FakeController(_base_ds()))
    rendered = recorder.joined()
    assert any(
        call.get("label") == "Preview codon metrics and expression frame"
        for call in recorder.button_calls
    )
    assert "External review draft available" not in rendered
