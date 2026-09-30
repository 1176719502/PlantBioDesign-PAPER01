from __future__ import annotations

import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from core.session_keys import SK
import components.export_manager as export_manager


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict = {}
        self.caption_messages: list[str] = []
        self.error_messages: list[str] = []
        self.download_calls: list[dict] = []

    def caption(self, message, **_kwargs):
        self.caption_messages.append(message)

    def error(self, message, **_kwargs):
        self.error_messages.append(message)

    def download_button(self, label, **kwargs):
        self.download_calls.append({"label": label, **kwargs})
        return False

    def button(self, label, **kwargs):
        return False

    def columns(self, count, **_kwargs):
        return [self for _ in range(count)]


def test_generate_fasta_string_exports_sequence_with_wrapped_body():
    fasta_text = export_manager.generate_fasta_string(
        sequence="ATGCATGC",
        project_name="Demo Construct",
    )

    assert fasta_text.startswith(">Demo_Construct\n")
    assert "ATGCATGC" in fasta_text


    gb_text = export_manager.generate_genbank_string(
        sequence="ATGCATGC",
        features=[
            {"name": "Demo CDS", "type": "CDS", "start": 1, "end": 8, "note": "representative"}
        ],
        project_name="Demo Construct",
    )

    assert "LOCUS" in gb_text
    assert "Demo_Construct" in gb_text
    assert "CDS" in gb_text
    assert "Demo CDS" in gb_text
    assert "representative" in gb_text
    assert "atgcatgc" in gb_text.lower()


def test_build_design_session_export_payload_uses_only_current_design_session(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            SK.ACTIVE_SEQ: "ATGOLD",
            SK.ACTIVE_FEATURES: [{"name": "Old feature", "type": "misc_feature", "start": 1, "end": 6}],
            SK.PROJECT_NAME: "Old Project",
        }
    )
    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setitem(
        sys.modules,
        "services.report_service",
        types.SimpleNamespace(generate_report_content=lambda ds: {"report_presenter": {}, "sequence": ds.frame["final_sequence"]}),
    )

    loaded_session = DesignSession(
        gene_name="Wizard GFP",
        original_seq="ATGAAA",
        optimized_seq="ATGCCC",
        frame={
            "success": True,
            "final_sequence": "ATGTTTAA",
            "parts": [
                {"name": "Promoter", "type": "promoter", "seq": "ATG"},
                {"name": "CDS", "type": "CDS", "seq": "TTTAA"},
            ],
        },
    )

    export_payload = export_manager.build_design_session_export_payload(loaded_session)

    assert export_payload["sequence"] == "ATGTTTAA"
    assert export_payload["project_name"] == "Wizard GFP"
    assert export_payload["genbank_features"] == [
        {"name": "Promoter", "label": "Promoter", "type": "promoter", "start": 1, "end": 3, "strand": 1},
        {"name": "CDS", "label": "CDS", "type": "CDS", "start": 4, "end": 8, "strand": 1},
    ]
    assert export_payload["plasmid_map_features"] == [
        {"label": "Promoter", "start": 0, "end": 3, "type": "promoter", "strand": 1},
        {"label": "CDS", "start": 3, "end": 8, "type": "CDS", "strand": 1},
    ]
    assert export_payload["payloads"]["fasta"]["data"].startswith(">Wizard_GFP")
    assert "genbank" in export_payload["payloads"]
    assert fake_st.session_state[SK.ACTIVE_SEQ] == "ATGOLD"



def test_resolve_active_export_payload_prefers_design_session_frame(monkeypatch):
    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            SK.ACTIVE_SEQ: "ATGOLD",
            SK.ACTIVE_FEATURES: [{"name": "Old feature", "type": "misc_feature", "start": 1, "end": 6}],
            SK.PROJECT_NAME: "Old Project",
        }
    )
    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setitem(
        sys.modules,
        "services.report_service",
        types.SimpleNamespace(generate_report_content=lambda ds: {"report_presenter": {}, "sequence": ds.frame["final_sequence"]}),
    )

    loaded_session = DesignSession(
        gene_name="Wizard GFP",
        original_seq="ATGAAA",
        optimized_seq="ATGCCC",
        frame={
            "success": True,
            "final_sequence": "ATGTTTAA",
            "parts": [
                {"name": "Promoter", "type": "promoter", "seq": "ATG"},
                {"name": "CDS", "type": "CDS", "seq": "TTTAA"},
            ],
        },
    )

    fake_session_controller = type(
        "_FakeSessionController",
        (),
        {"get": lambda self: loaded_session},
    )
    monkeypatch.setitem(
        sys.modules,
        "core.design_session",
        types.SimpleNamespace(SessionController=fake_session_controller),
    )

    seq, features, project_name = export_manager._resolve_active_export_payload()

    assert seq == "ATGTTTAA"
    assert project_name == "Wizard GFP"
    assert features == [
        {"name": "Promoter", "label": "Promoter", "type": "promoter", "start": 1, "end": 3, "strand": 1},
        {"name": "CDS", "label": "CDS", "type": "CDS", "start": 4, "end": 8, "strand": 1},
    ]
    assert fake_st.session_state[SK.ACTIVE_SEQ] == "ATGTTTAA"
    assert fake_st.session_state[SK.ACTIVE_FEATURES] == features
    assert fake_st.session_state[SK.PROJECT_NAME] == "Wizard GFP"


def test_render_export_button_surfaces_download_for_valid_sequence(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setattr(
        export_manager,
        "_resolve_active_export_payload",
        lambda: (
            "ATGCATGC",
            [{"name": "CDS", "type": "CDS", "start": 1, "end": 8}],
            "Demo Construct",
        ),
    )

    export_manager.render_export_button()

    assert fake_st.error_messages == []
    assert fake_st.caption_messages == []
    assert len(fake_st.download_calls) == 2
    labels = {call["label"] for call in fake_st.download_calls}
    assert labels == {"Export FASTA (.fasta)", "Export GenBank (.gb)"}
    fasta_call = next(call for call in fake_st.download_calls if call["label"] == "Export FASTA (.fasta)")
    genbank_call = next(call for call in fake_st.download_calls if call["label"] == "Export GenBank (.gb)")
    assert fasta_call["file_name"] == "Demo_Construct.fasta"
    assert fasta_call["data"].startswith(">Demo_Construct")
    assert genbank_call["file_name"] == "Demo_Construct.gb"
    assert "LOCUS" in genbank_call["data"]


def test_build_export_payloads_includes_fasta_and_genbank():
    payloads = export_manager.build_export_payloads(
        sequence="ATGCATGC",
        features=[{"name": "CDS", "type": "CDS", "start": 1, "end": 8}],
        project_name="Demo Construct",
    )

    assert set(payloads) == {"fasta", "genbank"}
    assert payloads["fasta"]["file_name"] == "Demo_Construct.fasta"
    assert payloads["fasta"]["data"].startswith(">Demo_Construct")
    assert payloads["genbank"]["file_name"] == "Demo_Construct.gb"
    assert "LOCUS" in payloads["genbank"]["data"]


def test_render_export_button_shows_caption_when_no_sequence(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(export_manager, "st", fake_st)
    monkeypatch.setattr(export_manager, "_resolve_active_export_payload", lambda: ("", [], "Untitled"))

    export_manager.render_export_button()

    assert fake_st.download_calls == []
    assert fake_st.error_messages == []
    assert len(fake_st.caption_messages) == 1
