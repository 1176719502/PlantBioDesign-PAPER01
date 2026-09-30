# -*- coding: utf-8 -*-
"""
Focused regression tests for Delivery-page localization.
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


class _Column(_Context):
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, label, value, *args, **kwargs):
        self.recorder.add(label, value)

    def download_button(self, label, *args, **kwargs):
        self.recorder.add(label, kwargs.get("help"))
        return False

    def button(self, label, *args, **kwargs):
        self.recorder.add(label, kwargs.get("help"))
        return False


class _FakeTextColumn:
    def __init__(self, label, help=None):
        self.label = label
        self.help = help


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder):
        self.recorder = recorder
        self.session_state = {}
        self.column_config = types.SimpleNamespace(TextColumn=_FakeTextColumn)

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, label, value, *args, **kwargs):
        self.recorder.add(label, value)

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_Column(self.recorder) for _ in range(count)]

    def expander(self, label, **kwargs):
        self.recorder.add(label)
        return _Context()

    def form(self, *args, **kwargs):
        return _Context()

    def radio(self, _label, options, **kwargs):
        return list(options)[0]

    def selectbox(self, _label, options, **kwargs):
        return list(options)[0] if options else None

    def text_input(self, _label, value="", **kwargs):
        return value

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def form_submit_button(self, label, **kwargs):
        self.recorder.add(label)
        return False

    def caption(self, body, **kwargs):
        self.recorder.add(body)

    def download_button(self, label, *args, **kwargs):
        self.recorder.add(label, kwargs.get("help"))
        return False

    def button(self, label, *args, **kwargs):
        self.recorder.add(label, kwargs.get("help"))
        return False

    def dataframe(self, *args, **kwargs):
        if args:
            try:
                self.recorder.add(args[0].to_string(index=False))
            except Exception:
                self.recorder.add(args[0])
        column_config = kwargs.get("column_config") or {}
        for key, config in column_config.items():
            self.recorder.add(key, getattr(config, "label", None), getattr(config, "help", None))

    def code(self, body, **kwargs):
        self.recorder.add(body)

    def pyplot(self, *args, **kwargs):
        return None

    def divider(self):
        return None

    def rerun(self):
        return None

    def error(self, body, **kwargs):
        self.recorder.add(body)


class _FakeController:
    def __init__(self, ds: DesignSession):
        self._ds = ds

    def get(self) -> DesignSession:
        return self._ds


def _build_delivery_session() -> DesignSession:
    ds = DesignSession(step=6)
    ds.gene_name = "DemoGene"
    ds.original_seq = "ATG" + ("GCC" * 20) + "TAA"
    ds.optimized_seq = ds.original_seq
    ds.host = "E.coli BL21(DE3)"
    ds.tag = "No tag"
    ds.elements = {
        "promoter_name": "T7",
        "rbs_name": "Strong RBS",
        "terminator_name": "rrnB T1",
    }
    ds.cloning_method = "Gibson"
    ds.primers = [{"name": "F1"}, {"name": "R1"}]
    ds.validation_results = [{"severity": "info", "message": "ok"}]
    ds.frame = {
        "success": True,
        "final_sequence": ds.original_seq,
        "total_length": len(ds.original_seq),
        "gc_content": 51.2,
        "vector_suggestion": "pET-28a",
        "parts": [
            {"name": "Promoter", "type": "promoter", "seq": "TTGACA"},
            {"name": "CDS", "type": "CDS", "seq": ds.original_seq},
        ],
        "features": [
            {"name": "CDS", "type": "CDS", "start": 1, "end": len(ds.original_seq)},
        ],
    }
    return ds


def test_delivery_page_localizes_user_facing_copy(monkeypatch):
    import views.wizard_steps.step6_export as step6_export
    import streamlit as st

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    monkeypatch.setattr(st, "session_state", fake_st.session_state)
    monkeypatch.setattr(st, "markdown", fake_st.markdown)
    monkeypatch.setattr(st, "metric", fake_st.metric)
    monkeypatch.setattr(st, "columns", fake_st.columns)
    monkeypatch.setattr(st, "expander", fake_st.expander)
    monkeypatch.setattr(st, "form", fake_st.form)
    monkeypatch.setattr(st, "radio", fake_st.radio)
    monkeypatch.setattr(st, "selectbox", fake_st.selectbox)
    monkeypatch.setattr(st, "text_input", fake_st.text_input)
    monkeypatch.setattr(st, "info", fake_st.info)
    monkeypatch.setattr(st, "form_submit_button", fake_st.form_submit_button)
    monkeypatch.setattr(st, "caption", fake_st.caption)
    monkeypatch.setattr(st, "download_button", fake_st.download_button)
    monkeypatch.setattr(st, "button", fake_st.button)
    monkeypatch.setattr(st, "dataframe", fake_st.dataframe)
    monkeypatch.setattr(st, "code", fake_st.code)
    monkeypatch.setattr(st, "pyplot", fake_st.pyplot)
    monkeypatch.setattr(st, "divider", fake_st.divider)
    monkeypatch.setattr(st, "rerun", fake_st.rerun)
    monkeypatch.setattr(st, "error", fake_st.error)
    monkeypatch.setattr(st, "column_config", fake_st.column_config)

    fake_report_service = types.SimpleNamespace(
        generate_report_content=lambda ds: {
            "meta": {
                "Gene / Construct": ds.gene_name,
                "Expression Host": ds.host,
                "Protein Tag": ds.tag,
                "Total Length (bp)": len(ds.original_seq),
                "GC Content (%)": 51.2,
                "Cloning Method": ds.cloning_method,
                "Vector Suggestion": "pET-28a",
                "Validation Issues": len(ds.validation_results),
            },
            "elements": [{"Source": "Registry"}],
            "primers": [{"Name": "F1", "Sequence (5'→3')": "ATGC", "Length": 4, "Tm": 55.0, "Role": "Forward"}],
        },
        render_markdown_report=lambda report: "# report",
    )
    import components.export_manager as real_export_manager

    fake_export_manager = types.SimpleNamespace(
        build_design_session_export_payload=real_export_manager.build_design_session_export_payload,
        build_export_manifest=real_export_manager.build_export_manifest,
        build_export_manifest_payload=real_export_manager.build_export_manifest_payload,
        render_export_button=lambda: recorder.add("Export GenBank (.gb)"),
    )
    fake_session_controller = type("_FakeSessionController", (), {"sync_to_global_state": lambda self: None})

    monkeypatch.setitem(sys.modules, "services.report_service", fake_report_service)
    monkeypatch.setitem(sys.modules, "components.export_manager", fake_export_manager)
    monkeypatch.setitem(
        sys.modules,
        "core.design_session",
        types.SimpleNamespace(DesignSession=DesignSession, SessionController=fake_session_controller),
    )

    step6_export.page(_FakeController(_build_delivery_session()))

    rendered = recorder.joined()

    expected_texts = [
        "Export Review",
        "Design record review",
        "Export files",
        "Download FASTA (.fasta)",
        "Download construct/cassette map (PNG)",
        "Save to dashboard",
        "documentation review",
    ]
    for expected_text in expected_texts:
        assert expected_text in rendered

    assert (
        "Validation complete - manual review remains open" in rendered
        or "Documentation checks completed - documentation review complete" in rendered
    )

    for disallowed_text in [
        "Delivery overview",
        "Design readiness overview",
        "Export package",
        "Download plasmid image (PNG)",
        "Save design",
        "Export GenBank file (.gb)",
        "Delivery complete",
        "Ready for final delivery",
    ]:
        assert disallowed_text not in rendered

    for allowed_term in ["FASTA", "GenBank", ".gb", "PNG", "RBS", "Kozak", "GC", "bp"]:
        assert allowed_term in rendered


def test_saved_state_copy_distinguishes_preview_export_from_documentation_review(monkeypatch):
    import views.wizard_steps.step6_export as step6_export
    import streamlit as st

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_p6_saved_name"] = "DemoGene"

    monkeypatch.setattr(st, "session_state", fake_st.session_state)
    monkeypatch.setattr(st, "markdown", fake_st.markdown)
    monkeypatch.setattr(st, "metric", fake_st.metric)
    monkeypatch.setattr(st, "columns", fake_st.columns)
    monkeypatch.setattr(st, "expander", fake_st.expander)
    monkeypatch.setattr(st, "form", fake_st.form)
    monkeypatch.setattr(st, "radio", fake_st.radio)
    monkeypatch.setattr(st, "selectbox", fake_st.selectbox)
    monkeypatch.setattr(st, "text_input", fake_st.text_input)
    monkeypatch.setattr(st, "info", fake_st.info)
    monkeypatch.setattr(st, "form_submit_button", fake_st.form_submit_button)
    monkeypatch.setattr(st, "caption", fake_st.caption)
    monkeypatch.setattr(st, "download_button", fake_st.download_button)
    monkeypatch.setattr(st, "button", fake_st.button)
    monkeypatch.setattr(st, "dataframe", fake_st.dataframe)
    monkeypatch.setattr(st, "code", fake_st.code)
    monkeypatch.setattr(st, "pyplot", fake_st.pyplot)
    monkeypatch.setattr(st, "divider", fake_st.divider)
    monkeypatch.setattr(st, "rerun", fake_st.rerun)
    monkeypatch.setattr(st, "error", fake_st.error)
    monkeypatch.setattr(st, "column_config", fake_st.column_config)

    fake_report_service = types.SimpleNamespace(
        generate_report_content=lambda ds: {"meta": {}, "elements": [], "primers": []},
        render_markdown_report=lambda report: "# report",
    )
    import components.export_manager as real_export_manager

    fake_export_manager = types.SimpleNamespace(
        build_design_session_export_payload=real_export_manager.build_design_session_export_payload,
        build_export_manifest=real_export_manager.build_export_manifest,
        build_export_manifest_payload=real_export_manager.build_export_manifest_payload,
        render_export_button=lambda: None,
    )
    fake_session_controller = type("_FakeSessionController", (), {"sync_to_global_state": lambda self: None})

    monkeypatch.setitem(sys.modules, "services.report_service", fake_report_service)
    monkeypatch.setitem(sys.modules, "components.export_manager", fake_export_manager)
    monkeypatch.setitem(sys.modules, "core.design_session", types.SimpleNamespace(SessionController=fake_session_controller))

    preview_only = _build_delivery_session()
    preview_only.validation_results = []
    step6_export.page(_FakeController(preview_only))
    rendered_preview = recorder.joined()

    assert "Design saved" in rendered_preview
    assert "available for preview and documentation-only export" in rendered_preview
    assert "review remains open" in rendered_preview

    recorder.texts.clear()
    final_ready = _build_delivery_session()
    step6_export.page(_FakeController(final_ready))
    rendered_final = recorder.joined()

    assert "Design saved" in rendered_final
    assert "documentation review complete" in rendered_final
    assert "reviewed design record" in rendered_final


def test_export_manager_localizes_messages_but_keeps_allowed_terms(monkeypatch):
    import components.export_manager as export_manager
    import streamlit as st

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)

    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setattr(export_manager, "_resolve_active_export_payload", lambda: ("ATGCATGC", [{"name": "CDS", "type": "CDS", "start": 1, "end": 8}], "Demo Construct"))
    monkeypatch.setattr(export_manager, "generate_genbank_string", lambda sequence, features, project_name: "LOCUS demo")

    export_manager.render_export_button()
    rendered = recorder.joined()

    assert "Export GenBank (.gb)" in rendered
    assert "Export FASTA (.fasta)" in rendered
    assert "SnapGene" in rendered
    assert "Benchling" in rendered
    assert "Geneious" in rendered
    assert "NCBI" in rendered
    assert "Export GenBank file (.gb)" not in rendered
    assert "Download the annotated construct as GenBank" in rendered
