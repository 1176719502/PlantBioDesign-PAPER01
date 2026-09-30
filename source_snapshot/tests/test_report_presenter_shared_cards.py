from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from views.wizard_steps._shared import (
    render_report_download_button,
    render_report_preview_container,
    render_report_preview_summary_cards,
    render_report_sequence_preview,
)
from services.report_service import build_report_presenter


class _DummyColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyExpander(_DummyColumn):
    pass


def test_shared_report_card_renderer_filters_step_keys(monkeypatch):
    presenter = {
        "summary_cards": [
            {"step_key": "step4", "title": "Step 4", "status_text": "Recommended", "level": "ready", "metrics": [{"label": "A", "value": 1}], "caption": "c4"},
            {"step_key": "step5", "title": "Step 5", "status_text": "passed", "level": "ready", "metrics": [{"label": "B", "value": 2}], "caption": "c5"},
            {"step_key": "step6", "title": "Step 6", "status_text": "Documentation Export Available", "level": "ready", "metrics": [{"label": "C", "value": 3}], "caption": "c6"},
        ]
    }

    calls = {"columns": 0, "metrics": [], "captions": []}

    class _DummyStreamlit:
        def markdown(self, *args, **kwargs):
            return None

        def columns(self, count):
            calls["columns"] = count
            return [_DummyColumn() for _ in range(count)]

        def metric(self, label, value):
            calls["metrics"].append((label, value))

        def caption(self, text):
            calls["captions"].append(text)

    import views.wizard_steps._shared as shared

    monkeypatch.setitem(sys.modules, "streamlit", _DummyStreamlit())
    render_report_preview_summary_cards(presenter, step_keys=["step4", "step5"])

    assert calls["columns"] == 2
    assert ("A", 1) in calls["metrics"]
    assert ("B", 2) in calls["metrics"]
    assert ("C", 3) not in calls["metrics"]
    assert "c4" in calls["captions"]
    assert "c5" in calls["captions"]
    assert "c6" not in calls["captions"]


def test_shared_report_sequence_preview_and_download_button(monkeypatch):
    presenter = {
        "sequence_preview": {
            "formatted": "ATGC\nGCTA",
        },
        "report_download": {
            "label": "Download design report (.md)",
            "filename": "demo_design_report.md",
            "mime": "text/markdown",
            "help": "report help",
        },
    }

    calls = {"code": [], "download": []}

    class _DummyStreamlit:
        def markdown(self, *args, **kwargs):
            return None

        def code(self, body, language=None):
            calls["code"].append((body, language))

        def download_button(self, **kwargs):
            calls["download"].append(kwargs)

    monkeypatch.setitem(sys.modules, "streamlit", _DummyStreamlit())
    render_report_sequence_preview(presenter, heading="Final construct sequence")
    render_report_download_button(presenter, "# report", button_key="report_btn")

    assert calls["code"] == [("ATGC\nGCTA", None)]
    assert calls["download"][0]["label"] == "Download design report (.md)"
    assert calls["download"][0]["file_name"] == "demo_design_report.md"
    assert calls["download"][0]["mime"] == "text/markdown"
    assert calls["download"][0]["key"] == "report_btn"


    presenter = {
        "overview_rows": [{"label": "Gene", "value": "DemoGene"}],
        "alignment_rows": [{"Section": "Step 4", "Status": "Recommended", "Details": "Ready"}],
        "download_rows": [{"Format": "Markdown Report (.md)", "Status": "Ready", "File": "demo.md"}],
        "summary_cards": [
            {"step_key": "step4", "title": "Step 4", "status_text": "Recommended", "level": "ready", "metrics": [{"label": "A", "value": 1}], "caption": "c4"},
            {"step_key": "step5", "title": "Step 5", "status_text": "passed", "level": "ready", "metrics": [{"label": "B", "value": 2}], "caption": "c5"},
        ],
    }

    calls = {"expanders": [], "columns": [], "dataframes": 0, "captions": [], "markdown": []}

    class _DummyStreamlit:
        def markdown(self, *args, **kwargs):
            calls["markdown"].append(args[0] if args else "")
            return None

        def expander(self, label, expanded=False):
            calls["expanders"].append((label, expanded))
            return _DummyExpander()

        def columns(self, spec, gap=None):
            count = spec if isinstance(spec, int) else len(spec)
            calls["columns"].append(count)
            return [_DummyColumn() for _ in range(count)]

        def dataframe(self, *args, **kwargs):
            calls["dataframes"] += 1

        def write(self, *args, **kwargs):
            return None

        def metric(self, *args, **kwargs):
            return None

        def caption(self, text):
            calls["captions"].append(text)

    monkeypatch.setitem(sys.modules, "streamlit", _DummyStreamlit())
    render_report_preview_container(presenter, step_keys=["step4", "step5"], section_title="Preview design report")

    assert calls["expanders"] == [("Preview design report", False)]
    assert calls["columns"] == [3, 2]
    assert calls["dataframes"] == 2
    assert any("Download availability" in text for text in calls["markdown"])
    assert not any("Download readiness" in text for text in calls["markdown"])
    assert any("Sequence Verification Summary" in text for text in calls["markdown"])
    assert "No sequence verification result was attached to this report." in calls["captions"]
    assert "c4" in calls["captions"]
    assert "c5" in calls["captions"]


def test_build_report_presenter_populates_shared_report_download_metadata():
    report = {
        "meta": {
            "Gene / Construct": "DemoGene",
            "Expression Host": "E.coli",
            "Protein Tag": "No tag",
            "Total Length (bp)": 120,
            "GC Content (%)": 50.0,
            "Cloning Method": "Gibson Assembly",
            "Vector Suggestion": "pET-28a",
            "Validation Issues": 1,
        },
        "elements": [],
        "sequence": "ATG" + ("GCC" * 39),
        "step_alignment": {
            "step4": {
                "section_title": "Step 4 · Primer design summary",
                "status": "Recommended",
                "quality_grade": "Recommended",
                "risk_counts": {"recommended": 1, "usable_with_risk": 0, "not_recommended": 0},
                "quality_reasons": ["Balanced primer Tm."],
                "pair_warnings": [],
            },
            "step5": {
                "section_title": "Step 5 · Validation summary",
                "status": "passed",
                "summary": "Documentation checks completed.",
                "issue_list": [{"Severity": "INFO"}],
                "risk_counts": {"recommended": 1, "usable_with_risk": 0, "not_recommended": 0},
                "affected_fragments": [],
                "top_risk_reasons": [],
            },
            "step6": {
                "section_title": "Step 6 · Export review status",
                "status": "Documentation Export Available",
                "recommendation": "Documentation Export Available",
                "conclusion": "Export is available for documentation review.",
                "action": "Download documentation files.",
                "risk_counts": {"critical": 0, "warning": 0, "primer_review_required": 0},
                "available_formats": [{"format": "markdown", "available": True}],
            },
        },
        "export_formats": {
            "available_formats": [
                {"label": "Markdown Report (.md)", "format": "markdown", "available": True, "filename": "demo.md"}
            ]
        },
        "sequence_verification": {
            "included": True,
            "message": "",
            "rows": [{"label": "Status", "value": "completed"}],
        },
    }

    presenter = build_report_presenter(report)

    assert presenter["cards_by_step"]["step4"]["title"] == "Step 4 · Assembly plan"
    assert presenter["cards_by_step"]["step5"]["title"] == "Step 5 · Validation summary"
    assert presenter["cards_by_step"]["step6"]["title"] == "Step 6 · Export review status"
    assert presenter["download_rows"][0]["Format"] == "Markdown Report (.md)"
    assert presenter["download_rows"][0]["Status"] == "Available"
    assert presenter["sequence_preview"]["heading"] == "Final construct sequence"
    assert presenter["sequence_preview"]["length_bp"] == 120
    assert presenter["report_download"]["filename"] == "DemoGene_design_report.md"
    assert presenter["sequence_verification"]["included"] is True
    assert presenter["sequence_verification"]["rows"][0]["value"] == "completed"
    assert [card["step_key"] for card in presenter["summary_cards"]] == ["step4", "step5", "step6"]


def test_step4_and_step5_use_shared_report_download_button_component():
    shared_helper = "render_report_download_button"
    module_paths = [
        os.path.join(ROOT, "views", "wizard_steps", "step4_cloning_primers.py"),
        os.path.join(ROOT, "views", "wizard_steps", "step5_validation.py"),
    ]

    for module_path in module_paths:
        with open(module_path, "r", encoding="utf-8") as handle:
            source = handle.read()

        tree = ast.parse(source)
        helper_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == shared_helper
        ]
        raw_download_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "st"
            and node.func.attr == "download_button"
        ]

        assert helper_calls, f"Expected {module_path} to call {shared_helper}."
        assert not raw_download_calls, f"Expected {module_path} to avoid direct st.download_button usage."
