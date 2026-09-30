# -*- coding: utf-8 -*-
"""
Focused regression tests for Step 3 English user-facing copy.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession


class _Recorder:
    def __init__(self):
        self.texts: list[str] = []

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
        self.session_state: dict[str, object] = {}

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
        self.recorder.add(label, kwargs.get("help"))
        return False

    def code(self, body, **kwargs):
        self.recorder.add(body)


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds

    def get(self) -> DesignSession:
        return self._ds

    def save(self, ds: DesignSession) -> None:
        self._ds = ds

    def advance(self) -> None:
        return None


def test_step3_uses_english_user_facing_copy(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)

    ds = DesignSession(
        step=3,
        gene_name="DemoGene",
        original_seq="ATG" + ("GCC" * 20) + "TAA",
        optimized_seq="ATG" + ("GCC" * 20) + "TAA",
        host="E.coli BL21(DE3)",
        tag="No tag",
        frame={},
    )

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(step3, "render_flow_strip", lambda items: recorder.add(*(value for pair in items for value in pair)))

    step3.page(_FakeController(ds))
    rendered = recorder.joined()

    for expected_text in [
        "Codon Usage Preview & Expression Frame",
        "Step 3 is metrics/readback only, not automatic optimization.",
        "Input overview",
        "Confirmed CDS plus host, tag, and regulatory context",
        "Original CDS (from Step 1)",
        "Original CDS preserved in preview",
        "The preview CDS currently matches the input sequence.",
        "Step 3 has not generated a synonymous recoding candidate.",
        "Primary action",
        "Build context recorded for review",
        "Preview codon metrics and expression frame",
        "Original CDS is preserved; no synonymous recoding candidate is generated unless you explicitly preview the separate draft below.",
        "Preview computational codon candidate draft",
        "page-session documentation review draft only",
        "Computational synonymous recoding candidates will be handled separately as review drafts when enabled.",
        "Result",
        "No expression-frame preview yet",
        "documentation-only review",
    ]:
        assert expected_text in rendered

    for disallowed_text in [
        "Codon Optimization & Expression Frame",
        "Codon " + "optimization and expression frame",
        "Run codon " + "optimization and assemble expression frame",
        "Run codon usage preview and assemble expression frame",
        "Preview CDS is a generated optimized sequence",
        "recommended CDS",
        "validated expression sequence",
        "build-ready expression frame",
        "Step overview",
        "Original CDS from Step 1",
        "Main action",
        "Build context is ready",
        "Build context ready",
        "Expression frame is ready",
        "No expression frame result yet",
    ]:
        assert disallowed_text not in rendered


def test_step3_build_button_requires_host_selection(monkeypatch):
    import views.wizard_steps.step3_expression_frame as step3

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    button_calls: list[dict[str, object]] = []

    ds = DesignSession(
        step=3,
        gene_name="DemoGene",
        original_seq="ATG" + ("GCC" * 20) + "TAA",
        optimized_seq="",
        host="",
        tag="No tag",
        frame={},
    )

    def _record_button(label, **kwargs):
        button_calls.append({"label": label, **kwargs})
        return False

    fake_st.button = _record_button

    monkeypatch.setattr(step3, "st", fake_st)
    monkeypatch.setattr(step3, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step3, "_status_panel", lambda *args, **kwargs: None)

    step3.page(_FakeController(ds))

    assert button_calls
    build_button = next(
        call for call in button_calls
        if call["label"] == "Preview codon metrics and expression frame"
    )
    assert build_button["disabled"] is True


def test_step3_module_does_not_depend_on_step2_module():
    step3_source = (Path(ROOT) / "views" / "wizard_steps" / "step3_expression_frame.py").read_text(encoding="utf-8")

    assert "step2_host_elements" not in step3_source
