from __future__ import annotations

import os
import sys
import types

from streamlit.testing.v1 import AppTest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services.report_service import build_report_presenter, generate_report_content
from views.wizard_steps.step5_validation import PRIMER_HIGH_RISK_CODE, PRIMER_REVIEW_CODE


class _Recorder:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.downloads: list[tuple[str, object]] = []

    def add(self, *values) -> None:
        for value in values:
            if value is not None:
                self.texts.append(str(value))

    def add_download(self, label: str, data) -> None:
        self.downloads.append((str(label), data))

    def joined(self) -> str:
        return "\n".join(self.texts)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Column(_Context):
    def __init__(self, recorder: _Recorder) -> None:
        self.recorder = recorder

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def metric(self, label, value, *args, **kwargs):
        self.recorder.add(label, value)

    def download_button(self, label, *args, **kwargs):
        data = kwargs.get("data")
        if data is None and args:
            data = args[0]
        self.recorder.add(label, kwargs.get("help"))
        self.recorder.add_download(label, data)
        return False

    def button(self, label, *args, **kwargs):
        self.recorder.add(label, kwargs.get("help"))
        return False


class _FakeTextColumn:
    def __init__(self, label, help=None):
        self.label = label
        self.help = help


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder) -> None:
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
        data = kwargs.get("data")
        if data is None and args:
            data = args[0]
        self.recorder.add(label, kwargs.get("help"))
        self.recorder.add_download(label, data)
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
        return None

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
    def __init__(self, ds: DesignSession) -> None:
        self._ds = ds

    def get(self) -> DesignSession:
        return self._ds


def _build_delivery_session_with_critical_issue() -> DesignSession:
    sequence = "ATG" + ("GCC" * 20) + "TAA"
    return DesignSession(
        step=6,
        gene_name="DemoGene",
        original_seq=sequence,
        optimized_seq=sequence,
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "T7",
            "rbs_name": "Strong RBS",
            "terminator_name": "rrnB T1",
        },
        frame={
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "gc_content": 51.2,
            "vector_suggestion": "pET-28a",
            "parts": [
                {"name": "Promoter", "type": "promoter", "seq": "TTGACA"},
                {"name": "CDS", "type": "CDS", "seq": sequence},
            ],
        },
        primers=[{"name": "F1"}, {"name": "R1"}],
        validation_results=[
            {
                "severity": "critical",
                "code": "FRAME_ERROR",
                "title": "Critical frame issue",
                "why": "A blocking issue is present.",
                "fix": "Resolve before delivery.",
            }
        ],
        cloning_method="Gibson",
    )


def _build_delivery_session(sequence: str | None = None, gene_name: str = "DemoGene") -> DesignSession:
    sequence = sequence or ("ATG" + ("GCC" * 20) + "TAA")
    return DesignSession(
        step=6,
        gene_name=gene_name,
        original_seq=sequence,
        optimized_seq=sequence,
        host="E.coli BL21(DE3)",
        tag="No tag",
        elements={
            "promoter_name": "T7",
            "rbs_name": "Strong RBS",
            "terminator_name": "rrnB T1",
        },
        frame={
            "success": True,
            "final_sequence": sequence,
            "total_length": len(sequence),
            "gc_content": 51.2,
            "vector_suggestion": "pET-28a",
            "parts": [
                {"name": "Promoter", "type": "promoter", "seq": "TTGACA"},
                {"name": "CDS", "type": "CDS", "seq": sequence},
            ],
        },
        primers=[{"name": "F1"}, {"name": "R1"}],
        validation_results=[{"severity": "info", "message": "ok"}],
        cloning_method="Gibson",
    )


def _patch_step6_dependencies(monkeypatch, fake_st, step6_export) -> None:
    import streamlit as st

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

    monkeypatch.setitem(
        sys.modules,
        "services.report_service",
        types.SimpleNamespace(
            generate_report_content=generate_report_content,
            render_markdown_report=lambda report: "# report",
        ),
    )
    import components.export_manager as real_export_manager

    monkeypatch.setitem(
        sys.modules,
        "components.export_manager",
        types.SimpleNamespace(
            build_design_session_export_payload=lambda ds: {
                "sequence": ds.frame.get("final_sequence") or ds.optimized_seq or ds.original_seq,
                "has_sequence": True,
                "report": generate_report_content(ds),
                "plasmid_map_features": [
                    {"label": "Promoter", "start": 0, "end": 6, "type": "promoter", "strand": 1},
                    {"label": "CDS", "start": 6, "end": len(ds.frame.get("final_sequence") or ds.original_seq), "type": "CDS", "strand": 1},
                ],
                "plasmid_map_title": f"{ds.gene_name} — {len(ds.frame.get('final_sequence') or ds.original_seq):,} bp",
                "payloads": {
                    "fasta": {
                        "data": f">{ds.gene_name.replace(' ', '_')}\n{ds.frame.get('final_sequence') or ds.original_seq}\n",
                        "file_name": f"{ds.gene_name.replace(' ', '_')}.fasta",
                        "mime": "text/plain",
                    },
                    "genbank": {
                        "data": "LOCUS       DEMO\nFEATURES             Location/Qualifiers\n",
                        "file_name": f"{ds.gene_name.replace(' ', '_')}.gb",
                        "mime": "text/plain",
                    },
                },
                "png_filename": f"{ds.gene_name.replace(' ', '_')}_plasmid_map.png",
            },
            build_export_manifest=real_export_manager.build_export_manifest,
            build_export_manifest_payload=real_export_manager.build_export_manifest_payload,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "core.design_session",
        types.SimpleNamespace(
            DesignSession=DesignSession,
            SessionController=type(
                "_FakeSessionController",
                (),
                {"sync_to_global_state": lambda self: None},
            )
        ),
    )


def test_step6_catalog_context_readback_rows_keep_documentation_boundary():
    import views.wizard_steps.step6_export as step6_export

    rows = step6_export._catalog_context_readback_rows(
        [
            {
                "asset_label": "Plant promoter source note",
                "asset_id": "promoter-context-1",
                "source_label": "source review context not recorded",
                "documentation_status": "human review needed",
            },
            {
                "asset_label": "Pinned source record",
                "asset_id": "source-record-2",
                "source_label": "Curated source note",
                "documentation_status": "Reviewed documentation note",
            },
        ]
    )

    assert rows[0]["Catalog context"] == "Plant promoter source note"
    assert rows[0]["Source/review context"] == "Source: source review context not recorded; review: human review needed"
    assert rows[0]["Metadata gap"] == "source/review metadata gap present"
    assert rows[1]["Metadata gap"] == "source/review evidence metadata recorded"

    rendered = str(rows)
    assert "documentation context only" in rendered
    assert "not a biological recommendation" in rendered
    assert "not an optimization result" in rendered
    assert "not an experimental validation" in rendered
    assert "not a wet-lab readiness judgment" in rendered
    unsafe_terms = [
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "best " + "promoter",
    ]
    for term in unsafe_terms:
        assert term not in rendered.lower()


def test_step6_map_feature_readback_rows_keep_documentation_preview_boundary():
    import views.wizard_steps.step6_export as step6_export

    rows = step6_export._build_map_feature_readback_rows(
        [
            {
                "label": "T7 promoter",
                "type": "promoter",
                "start": 0,
                "end": 6,
                "strand": 1,
                "source_status": "Component Library source note recorded",
                "review_status": "Documentation review recorded",
            },
            {
                "label": "Reverse tag",
                "type": "tag",
                "start": 6,
                "end": 21,
                "strand": -1,
            },
        ],
        72,
    )

    assert rows[0]["Feature"] == "T7 promoter"
    assert rows[0]["Type"] == "promoter"
    assert rows[0]["Direction"] == "forward"
    assert rows[0]["Source/provenance"] == "Component Library source note recorded"
    assert rows[0]["Review status"] == "Documentation review recorded"
    assert rows[1]["Direction"] == "reverse"
    assert rows[1]["Source/provenance"] == "Source/provenance status not recorded"
    assert rows[1]["Review status"] == "Manual documentation review needed"
    rendered = str(rows)
    assert "approximate documentation readback" in rendered
    for unsafe in [
        "validated plasmid",
        "cloning-ready",
        "wet-lab ready",
        "optimized vector",
        "recommended plasmid",
        "guaranteed expression",
        "experimental success",
        "sequence verified",
    ]:
        assert unsafe not in rendered.lower()


def test_step6_minimal_map_feature_set_marks_manual_follow_up():
    import views.wizard_steps.step6_export as step6_export

    features = [{"label": "DemoGene", "type": "cds", "start": 0, "end": 72, "strand": 1}]

    assert step6_export._is_minimal_map_feature_set(features, 72) is True
    rows = step6_export._build_map_feature_readback_rows(features, 72)

    assert rows[0]["Review status"] == "Manual feature documentation follow-up"
    assert "approximate documentation readback" in rows[0]["Position/order note"]


def test_delivery_page_renders_single_export_entry_from_unified_payload(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_plasmid_fig"] = object()
    fake_st.session_state["wf_plasmid_png_signature"] = "stable"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    monkeypatch.setattr(step6_export, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_review_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_status_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_plasmid_png_signature", lambda *args, **kwargs: "stable")

    step6_export.page(_FakeController(_build_delivery_session()))

    labels = [label for label, _ in recorder.downloads]
    assert labels.count("Download FASTA (.fasta)") == 1
    assert labels.count("Download GenBank (.gb)") == 1
    assert labels.count("Download construct/cassette map (PNG)") == 1
    assert labels.count("Download design report (.md)") == 1


    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    status_calls: list[tuple[str, str, str]] = []

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    monkeypatch.setattr(step6_export, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_review_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        step6_export,
        "_status_panel",
        lambda title, body, tone="info": status_calls.append((title, body, tone)),
    )

    step6_export.page(_FakeController(_build_delivery_session_with_critical_issue()))

    assert status_calls, "Expected the delivery page to emit readiness status panels."
    first_status = status_calls[0]
    assert first_status[0] == "Review blocked by unresolved risk signals"
    assert first_status[2] == "warn"


def test_delivery_page_fake_streamlit_keeps_following_app_test_outside_form(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_plasmid_fig"] = object()
    fake_st.session_state["wf_plasmid_png_signature"] = "stable"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)
    monkeypatch.setattr(step6_export, "_step_header", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_section_label", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_review_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_status_panel", lambda *args, **kwargs: None)
    monkeypatch.setattr(step6_export, "_plasmid_png_signature", lambda *args, **kwargs: "stable")

    step6_export.page(_FakeController(_build_delivery_session()))
    monkeypatch.undo()

    app = AppTest.from_string(
        'import streamlit as st\nst.button("Registry isolation probe", disabled=True)'
    ).run()
    assert list(app.exception) == []
    assert app.button[0].label == "Registry isolation probe"
    assert app.button[0].disabled is True


def test_delivery_page_renders_documentation_map_readback_and_safe_png_copy(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_plasmid_fig"] = object()
    fake_st.session_state["wf_plasmid_png_signature"] = "stable"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    monkeypatch.setattr(step6_export, "_plasmid_png_signature", lambda *args, **kwargs: "stable")

    step6_export.page(_FakeController(_build_delivery_session()))

    rendered = recorder.joined().lower()
    assert "construct/cassette map preview" in rendered
    assert "documentation map preview for construct/cassette handoff review" in rendered
    assert "feature order preview" in rendered
    assert "source/provenance status not recorded" in rendered
    assert "manual documentation review needed" in rendered
    assert "approximate documentation readback" in rendered
    assert "download construct/cassette map (png)" in rendered
    assert "not sequence validation" in rendered
    assert "not cloning feasibility verification" in rendered
    assert "not experimental readiness approval" in rendered
    for unsafe in [
        "validated plasmid",
        "cloning-ready",
        "wet-lab ready",
        "optimized vector",
        "recommended plasmid",
        "guaranteed expression",
        "experimental success",
        "sequence verified",
    ]:
        assert unsafe not in rendered


def test_delivery_page_uses_documentation_review_label_in_status_caption(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    step6_export.page(_FakeController(_build_delivery_session_with_critical_issue()))

    rendered = recorder.joined()
    assert "Artifact generation status:" in rendered
    assert "documentation review open" in rendered
    assert "Readiness: preview ready" not in rendered
    assert " · Final delivery not ready" not in rendered
    assert "final delivery not ready" not in rendered


def test_delivery_page_shows_not_recommended_for_primer_high_risk(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Quality Grade": "Not Recommended",
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pair(s) detected",
            "why": "High-risk primer result carried over.",
            "fix": "Return to Step 4.",
        },
        {"severity": "info", "code": "PASS", "title": "All validation checks passed"},
    ]

    step6_export.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Review blocked by unresolved risk signals" in rendered
    assert "Documentation Export Available" not in rendered
    assert "Current review status: review blocked by unresolved risk signals." in rendered


def test_delivery_page_does_not_add_construct_readiness_certification_terms(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Quality Grade": "Not Recommended",
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pair(s) detected",
            "why": "High-risk primer result carried over.",
            "fix": "Return to Step 4.",
        }
    ]
    step6_export.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Review blocked by unresolved risk signals" in rendered
    assert "Validated" not in rendered
    assert "Certified" not in rendered


def test_delivery_page_shows_review_required_for_primer_review(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Quality Grade": "Usable with Risk",
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review recommended",
            "why": "Review-level primer risk carried over.",
            "fix": "Review Step 4.",
        }
    ]

    step6_export.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Export with Review Required" in rendered
    assert "Not Recommended for Experimental Use" not in rendered


def test_delivery_page_shows_ready_for_export_when_only_info_is_present(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    step6_export.page(_FakeController(_build_delivery_session()))

    rendered = recorder.joined()
    assert "Documentation Export Available" in rendered
    assert "Export with Review Required" not in rendered
    assert "Not Recommended for Experimental Use" not in rendered


def test_report_structure_contains_step4_step5_step6_sections():
    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragA",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 60.0,
            "Rev Anneal Tm (°C)": 60.0,
            "Fwd Arm (bp)": 24,
            "Rev Arm (bp)": 24,
            "Quality Grade": "Recommended",
            "Quality Reasons": ["Balanced primer Tm."],
            "Warnings": [],
        }
    ]
    report = generate_report_content(ds)

    assert "primer_quality" in report
    assert "validation_results" in report
    assert "export_recommendation" in report
    assert "step_alignment" in report
    assert "report_presenter" in report
    assert report["primer_quality"]["quality_grade"] == "Recommended"
    assert report["validation_results"]["final_conclusion"]["status"] == "passed"
    assert report["export_recommendation"]["recommendation"] == "Documentation Export Available"
    assert report["step_alignment"]["step4"]["status"] == "Recommended"
    assert report["step_alignment"]["step5"]["status"] == "passed"
    assert report["step_alignment"]["step6"]["status"] == "Documentation Export Available"


def test_delivery_page_renders_report_preview_summary_cards(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 58.0,
            "Rev Anneal Tm (°C)": 60.0,
            "Fwd Arm (bp)": 20,
            "Rev Arm (bp)": 20,
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Annealing Tm is slightly offset from target (60.0°C)."],
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review recommended",
            "why": "Review-level primer risk carried over.",
            "fix": "Review Step 4.",
        }
    ]

    step6_export.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Report summary cards" in rendered
    assert "Step 4 · Assembly plan" in rendered
    assert "Step 5 · Validation summary" in rendered
    assert "Step 6 · Export review status" in rendered
    assert "Usable with Risk" in rendered
    assert "Export with Review Required" in rendered
    assert "background:#fffbeb" in rendered
    assert "border:1px solid #fde68a" in rendered



def test_report_presenter_uses_artifact_language_for_report_generation_status():
    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Review primer context before export."],
        }
    ]

    report = generate_report_content(ds)
    presenter = build_report_presenter(report)
    rendered = str(presenter)

    assert "Assembly plan notes:" in rendered
    assert "Readiness: Ready" not in rendered
    assert "Download readiness" not in rendered
    assert "Report readiness" not in rendered


def test_report_markdown_does_not_use_readiness_ready_for_artifact_availability():
    ds = _build_delivery_session()
    report = generate_report_content(ds)
    from services.report_service import render_markdown_report

    markdown = render_markdown_report(report)

    assert "Readiness: Ready" not in markdown
    assert "Download readiness" not in markdown
    assert "Report readiness" not in markdown
    assert "Ready / Validated / Certified" not in markdown


def test_report_presenter_reuses_step_alignment_data_for_preview_cards():
    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Fwd Anneal Tm (°C)": 58.0,
            "Rev Anneal Tm (°C)": 60.0,
            "Fwd Arm (bp)": 20,
            "Rev Arm (bp)": 20,
            "Quality Grade": "Usable with Risk",
            "Quality Reasons": ["Annealing Tm is slightly offset from target (60.0°C)."],
            "Warnings": ["Moderate cross-dimer risk between primers."],
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review recommended",
            "why": "Review-level primer risk carried over.",
            "fix": "Review Step 4.",
        }
    ]

    report = generate_report_content(ds)
    presenter = build_report_presenter(report)

    assert presenter["cards_by_step"]["step4"]["status_text"] == report["step_alignment"]["step4"]["status"]
    assert presenter["cards_by_step"]["step5"]["status_text"] == report["step_alignment"]["step5"]["status"]
    assert presenter["cards_by_step"]["step6"]["status_text"] == report["step_alignment"]["step6"]["status"]


def test_step6_cached_report_payload_is_deterministic(monkeypatch):
    import json
    import views.wizard_steps.step6_export as step6_export

    report = generate_report_content(_build_delivery_session())
    report_json = json.dumps(report, ensure_ascii=False, sort_keys=True, default=str)

    monkeypatch.setattr(
        step6_export,
        '_build_cached_report_payload',
        lambda report_signature, report_json_arg: {
            'signature': report_signature,
            'report': json.loads(report_json_arg),
            'markdown': '# cached report',
            'presenter': json.loads(report_json_arg).get('report_presenter') or {},
        },
    )

    first = step6_export._build_cached_report_payload('sig-1', report_json)
    second = step6_export._build_cached_report_payload('sig-1', report_json)

    assert first['signature'] == second['signature'] == 'sig-1'
    assert first['markdown'] == second['markdown'] == '# cached report'
    assert first['presenter'] == second['presenter']


def test_delivery_page_renders_red_risk_card_for_not_recommended(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    ds = _build_delivery_session()
    ds.primers = [
        {
            "Fragment Name": "FragHighRisk",
            "Forward Primer (5'->3')": "ATGCGTATGCGTATGCGTAT",
            "Reverse Primer (5'->3')": "CGCATACGCATACGCATACA",
            "Quality Grade": "Not Recommended",
            "Quality Reasons": ["High cross-dimer risk between primers (8 bp complementarity)."],
            "Warnings": ["High cross-dimer risk between primers (8 bp complementarity)."],
        }
    ]
    ds.validation_results = [
        {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pair(s) detected",
            "why": "Step 4 marked 1 primer pair as Not Recommended.",
            "fix": "Return to Step 4.",
        }
    ]

    step6_export.page(_FakeController(ds))

    rendered = recorder.joined()
    assert "Not Recommended" in rendered
    assert "Review blocked by unresolved risk signals" in rendered
    assert "background:#fef2f2" in rendered
    assert "border:1px solid #fecaca" in rendered


def test_delivery_page_refreshes_png_cache_only_when_construct_changes(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    stale_png = b"stale-png"
    fake_st.session_state["wf_plasmid_png"] = stale_png

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    render_calls: list[tuple[str, tuple[tuple[str, int, int, str], ...], str]] = []

    def _fake_render(seq, feats, title):
        normalized = tuple((f["label"], f["start"], f["end"], f["type"]) for f in feats)
        render_calls.append((seq, normalized, title))
        png = f"png-{len(render_calls)}".encode("utf-8")
        return None, png

    monkeypatch.setattr(step6_export, "_render_plasmid_png", _fake_render)

    from components.export_manager import build_design_session_export_payload

    session_a = _build_delivery_session()
    export_payload_a = build_design_session_export_payload(session_a)
    feats_a = export_payload_a["plasmid_map_features"]
    title_a = export_payload_a["plasmid_map_title"]
    fake_st.session_state["wf_plasmid_png_signature"] = step6_export._plasmid_png_signature(session_a.frame["final_sequence"], feats_a, title_a)

    step6_export.page(_FakeController(session_a))

    assert fake_st.session_state["wf_plasmid_png"] != stale_png
    assert [data for label, data in recorder.downloads if label == "Download construct/cassette map (PNG)"][-1] == fake_st.session_state["wf_plasmid_png"]
    assert len(render_calls) == 1

    session_b = _build_delivery_session(sequence="ATG" + ("GAA" * 20) + "TAA", gene_name="DemoGeneV2")
    step6_export.page(_FakeController(session_b))

    assert fake_st.session_state["wf_plasmid_png"] != stale_png
    refreshed_png = fake_st.session_state["wf_plasmid_png"]
    assert [data for label, data in recorder.downloads if label == "Download construct/cassette map (PNG)"][-1] == refreshed_png
    assert len(render_calls) == 2

    empty_session = DesignSession(step=6, gene_name="EmptyConstruct")
    fake_st.session_state["wf_plasmid_png"] = b"old-png"
    fake_st.session_state["wf_plasmid_png_signature"] = "old-signature"
    step6_export.page(_FakeController(empty_session))

    assert "wf_plasmid_png" not in fake_st.session_state
    assert "wf_plasmid_png_signature" not in fake_st.session_state


def test_saved_state_copy_distinguishes_preview_export_from_documentation_review(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_p6_saved_name"] = "DemoGene"

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    preview_only = _build_delivery_session()
    preview_only.validation_results = []
    step6_export.page(_FakeController(preview_only))
    rendered_preview = recorder.joined()

    assert "documentation review open" in rendered_preview
    assert "final delivery not ready" not in rendered_preview

    recorder.texts.clear()
    final_ready = _build_delivery_session()
    step6_export.page(_FakeController(final_ready))
    rendered_final = recorder.joined()

    assert "documentation review complete" in rendered_final
    assert "final delivery ready" not in rendered_final


def test_delivery_summary_falls_back_to_frame_element_names(monkeypatch):
    import views.wizard_steps.step6_export as step6_export

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    fake_st.session_state["wf_plasmid_png"] = b"png-bytes"
    fake_st.session_state["wf_plasmid_fig"] = object()

    _patch_step6_dependencies(monkeypatch, fake_st, step6_export)

    session = _build_delivery_session()
    session.elements = {}
    session.frame["promoter_name"] = "T7 Promoter"
    session.frame["rbs_name"] = "Shine-Dalgarno B0034"
    session.frame["terminator_name"] = "rrnB T1 Terminator"

    step6_export.page(_FakeController(session))
    rendered = recorder.joined()

    assert "T7 Promoter" in rendered
    assert "Shine-Dalgarno B0034" in rendered
    assert "rrnB T1 Terminator" in rendered


def test_export_manager_localizes_messages_but_keeps_allowed_terms(monkeypatch):
    import components.export_manager as export_manager

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setattr(export_manager, "_resolve_active_export_payload", lambda: ("ATGCATGC", [{"name": "CDS", "type": "CDS", "start": 1, "end": 8}], "Demo Construct"))
    monkeypatch.setattr(export_manager, "generate_genbank_string", lambda sequence, features, project_name: "LOCUS demo")

    export_manager.render_export_button()
    rendered = recorder.joined()

    assert "Export GenBank (.gb)" in rendered
    assert "Export FASTA (.fasta)" in rendered
    assert "Benchling" in rendered
    assert "Geneious" in rendered
    assert "NCBI" in rendered
    assert "导出 GenBank (.gb)" not in rendered
