# -*- coding: utf-8 -*-
"""
Focused regression tests for Step 2 localization cleanup.
"""
from __future__ import annotations

import os
import sys
import types

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


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder
        self.session_state: dict[str, object] = {}

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def caption(self, body, **kwargs):
        self.recorder.add(body)

    def warning(self, body, **kwargs):
        self.recorder.add(body)

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def error(self, body, **kwargs):
        self.recorder.add(body)

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Context() for _ in range(count)]

    def expander(self, label, **kwargs):
        self.recorder.add(label)
        return _Context()

    def selectbox(self, label, options, index=0, key=None, format_func=None, **kwargs):
        self.recorder.add(label)
        if format_func is not None and options:
            self.recorder.add(*(format_func(option) for option in options[:1]))
        if key is not None and key in self.session_state and self.session_state[key] in options:
            value = self.session_state[key]
        else:
            value = options[index] if options else None
        self.recorder.add(value)
        if key is not None:
            self.session_state[key] = value
        return value

    def text_input(self, label, value="", key=None, placeholder=None, **kwargs):
        self.recorder.add(label, placeholder)
        if key is not None and key in self.session_state:
            current = self.session_state[key]
        else:
            current = value
        if key is not None:
            self.session_state[key] = current
        return current

    def button(self, label, key=None, help=None, **kwargs):
        self.recorder.add(label, help)
        return False


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds

    def get(self) -> DesignSession:
        return self._ds

    def save(self, ds: DesignSession) -> None:
        self._ds = ds

    def advance(self) -> None:
        return None


def _build_step2_session() -> DesignSession:
    ds = DesignSession(step=2)
    ds.original_seq = "ATG" + ("GCC" * 20) + "TAA"
    ds.host = "E.coli BL21(DE3)"
    ds.tag = "No tag"
    ds.elements = {
        "promoter_name": "T7 Promoter",
        "promoter_seq": "TAATACGACTCACTATA",
        "rbs_name": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "terminator_name": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
    }
    ds.frame = {}
    ds.optimized_seq = ""
    ds.primers = []
    ds.validation_results = []
    return ds


def test_step2_uses_english_user_facing_copy(monkeypatch):
    import views.wizard_steps.step2_host_elements as step2_host_elements

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(step2_host_elements, "st", fake_st)
    monkeypatch.setattr(step2_host_elements, "_step_header", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step2_host_elements, "_section_label", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(step2_host_elements, "_status_panel", lambda *args, **kwargs: recorder.add(*args))
    monkeypatch.setattr(
        step2_host_elements,
        "_db_parts_map_for_host",
        lambda _host, part_types: {
            "Promoter": [{"name": "T7 Promoter", "sequence": "TAATACGACTCACTATA", "length_bp": 17}],
            "RBS": [{"name": "Shine-Dalgarno B0034", "sequence": "AAAGAGGAGAAA", "length_bp": 12}],
            "Terminator": [{"name": "rrnB T1 Terminator", "sequence": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT", "length_bp": 43}],
        },
    )

    fake_rules = {
        "kingdom": "prokaryote",
        "promoter": "T7 Promoter",
        "promoter_seq": "TAATACGACTCACTATA",
        "promoter_note": "T7 phage promoter requires BL21(DE3) strain. IPTG inducible (0.1-1 mM). Yield can reach 30-50% of total protein.",
        "rbs": "Shine-Dalgarno B0034",
        "rbs_seq": "AAAGAGGAGAAA",
        "rbs_note": "Strong Shine-Dalgarno. Optimal spacing to ATG: 6-8 bp. This design: 7 bp.",
        "terminator": "rrnB T1 Terminator",
        "terminator_seq": "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT",
        "terminator_note": "E.coli rrnB T1 Rho-independent terminator.",
        "tag_options": {"No tag": "", "His6-tag (C-term)": "CACCACCACCACCACCAC"},
        "vector_suggestion": "pET-28a or pET-21a",
        "gc_optimal": (40, 65),
    }
    monkeypatch.setitem(
        sys.modules,
        "core.expression_frame_builder",
        types.SimpleNamespace(
            get_host_groups=lambda: {"Bacteria": ["E.coli BL21(DE3)"]},
            get_host_rules=lambda host: fake_rules,
        ),
    )

    step2_host_elements.page(_FakeController(_build_step2_session()))

    rendered = recorder.joined()

    for expected_text in [
        "Advanced overrides",
        "Leave a field empty to keep the host default.",
        "Promoter sequence override (Part Registry)",
        "RBS / Kozak sequence override (Part Registry)",
        "Terminator sequence override (Part Registry)",
        "Promoter display name (label only)",
        "RBS / Kozak display name (label only)",
        "Terminator display name (label only)",
        "Sequence applied to construct:",
        "Vector review note:",
        "Target GC review range:",
        "Induction mode:",
        "Confirm host & regulatory elements",
        "Host selection recorded for this step",
        "Confirm this step to carry the selected host context into expression-frame assembly.",
    ]:
        assert expected_text in rendered

    for disallowed_text in [
        "Advanced override options",
        "Leave the field empty to use the host default.",
        "Promoter display label only",
        "RBS / Kozak display label only",
        "Terminator display label only",
        "Applied sequence in construct:",
        "Suggested plasmid vector:",
        "GC target:",
        "Induction method:",
        "Confirm host and regulatory elements",
        "Host selection is complete",
        "The host is ready. Confirm this step to continue to expression-frame assembly.",
    ]:
        assert disallowed_text not in rendered

    for allowed_term in ["T7", "B0034", "RBS", "Kozak", "GC", "bp", "E.coli BL21(DE3)"]:
        assert allowed_term in rendered

    for disallowed_authority_term in [
        "compatible candidate",
        "compatibility status",
        "candidate host:",
        "host is ready",
        "recommended",
        "best",
        "optimal",
        "safe for use",
    ]:
        assert disallowed_authority_term not in rendered.lower()
