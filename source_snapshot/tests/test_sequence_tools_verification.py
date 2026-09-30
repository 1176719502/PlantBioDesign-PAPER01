# -*- coding: utf-8 -*-
"""UI regression tests for the Sequence Tools verification panel."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


VALID_SEQ = (
    "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
    "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
)


class _Recorder:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.button_calls: list[dict[str, object]] = []
        self.selectbox_calls: list[dict[str, object]] = []
        self.button_map: dict[str, bool] = {}
        self.selectbox_values: dict[str, str] = {}
        self.session_state: dict[str, object] = {}
        self.dataframe_calls = 0

    def add(self, *values) -> None:
        for value in values:
            if value is not None:
                self.texts.append(str(value))

    def joined(self) -> str:
        return "\n".join(self.texts)


class _FakeColumn:
    def __init__(self, recorder: _Recorder) -> None:
        self.recorder = recorder

    def metric(self, *args, **kwargs):
        self.recorder.add(*args)

    def markdown(self, body, **kwargs):
        self.recorder.add(body)

    def caption(self, body, **kwargs):
        self.recorder.add(body)

    def info(self, body, **kwargs):
        self.recorder.add(body)

    def warning(self, body, **kwargs):
        self.recorder.add(body)


class _FakeStreamlit:
    def __init__(self, recorder: _Recorder) -> None:
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

    def write(self, *args, **kwargs):
        self.recorder.add(*args)

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [_FakeColumn(self.recorder) for _ in range(count)]

    def button(self, label, **kwargs):
        self.recorder.button_calls.append({"label": label, **kwargs})
        return self.recorder.button_map.get(kwargs.get("key"), False)

    def selectbox(self, label, options, **kwargs):
        self.recorder.add(label, *options)
        self.recorder.selectbox_calls.append({"label": label, "options": list(options), **kwargs})
        key = kwargs.get("key")
        if key in self.recorder.selectbox_values:
            return self.recorder.selectbox_values[key]
        index = int(kwargs.get("index", 0) or 0)
        return list(options)[index]

    def text_area(self, label, **kwargs):
        self.recorder.add(label, kwargs.get("placeholder"))
        key = kwargs.get("key")
        return str(self.recorder.session_state.get(key, ""))

    def file_uploader(self, label, **kwargs):
        self.recorder.add(label)
        return None

    def dataframe(self, *args, **kwargs):
        self.recorder.dataframe_calls += 1
        self.recorder.add("DATAFRAME_RENDERED")


def test_local_registry_completed_for_current_sequence_does_not_show_stale(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert "Status" in output
    assert "completed" in output
    assert sequence_tools.SEQUENCE_TOOLS_VERIFICATION_STALE_MESSAGE not in output
    result = recorder.session_state[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY]
    assert result["query"]["signature"] == sequence_tools._sequence_signature(VALID_SEQ)


def test_verification_result_shows_stale_after_sequence_change(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    initial_signature = sequence_tools._sequence_signature(VALID_SEQ)
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY] = {
        "status": "completed",
        "query": {"length": len(VALID_SEQ), "signature": initial_signature},
        "database": {"source": sequence_tools.SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE},
        "adapter_name": "local-parts-registry",
        "top_hit": None,
        "hits": [],
        "warnings": [],
        "timestamp": "2026-01-01T00:00:00Z",
        "disclaimer": sequence_tools.SEQUENCE_VERIFICATION_DISCLAIMER,
    }
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ + "GCT")

    assert sequence_tools.SEQUENCE_TOOLS_VERIFICATION_STALE_MESSAGE in recorder.joined()


def test_verification_result_clears_stale_after_rerun_for_changed_sequence(monkeypatch):
    import views.SequenceTools as sequence_tools

    changed_seq = VALID_SEQ + "GCT"
    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY] = {
        "status": "completed",
        "query": {"length": len(VALID_SEQ), "signature": sequence_tools._sequence_signature(VALID_SEQ)},
        "database": {"source": sequence_tools.SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE},
        "adapter_name": "local-parts-registry",
        "top_hit": None,
        "hits": [],
        "warnings": [],
        "timestamp": "2026-01-01T00:00:00Z",
        "disclaimer": sequence_tools.SEQUENCE_VERIFICATION_DISCLAIMER,
    }
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(changed_seq)

    output = recorder.joined()
    result = recorder.session_state[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY]
    assert result["query"]["signature"] == sequence_tools._sequence_signature(changed_seq)
    assert sequence_tools.SEQUENCE_TOOLS_VERIFICATION_STALE_MESSAGE not in output


def test_sequence_tools_renders_verification_section_without_running(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert "Sequence Verification" in output
    assert "Verification source" in output
    assert "Local Parts Registry" in output
    assert "Imported BLAST TSV" in output
    assert "Placeholder adapter" in output
    assert "BLAST-style similarity evidence" in output
    assert "Run Verification" in str(recorder.button_calls)
    assert "does not certify experimental readiness" in output
    assert "No verification result has been generated yet." in output


def test_run_verification_shows_disclaimer_and_does_not_expose_agent_behavior(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    before_state = dict(recorder.session_state)
    sequence_tools._render_verification_panel(VALID_SEQ)
    after_state = dict(recorder.session_state)

    output = recorder.joined()
    assert recorder.selectbox_calls[0]["options"][0] == "Local Parts Registry"
    assert "Sequence verification is informational only" in output
    assert "does not change validation status" in output
    assert "does not override primer or export safety recommendations" in output
    assert "Query length" in output
    assert "Database/source" in output
    assert "Status" in output
    assert "Local Parts Registry" in output
    assert "LOCAL_REGISTRY_ONLY" in output
    assert "agent" not in output.lower()
    assert "auto-design" not in output.lower()
    assert "apply recommendation" not in output.lower()
    assert "Validate" not in output
    assert "Approve" not in output
    assert set(after_state) - set(before_state) == {
        sequence_tools.SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY,
        sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SIGNATURE_KEY,
    }


def test_run_verification_displays_local_hit_table(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _FakeAdapter:
        name = "local-parts-registry"

        def verify(self, sequence: str, database_label: str) -> dict:
            return {
                "hits": [
                    {
                        "accession": "part-001",
                        "organism": "E.coli",
                        "description": "Local fixture part",
                        "percent_identity": 100.0,
                        "coverage": 100.0,
                        "e_value": "local_exact",
                        "alignment_length": len(sequence),
                        "alignment_summary": "Local registry exact match with fixture over 96 bp.",
                        "match_type": "exact_match",
                        "part_type": "CDS",
                        "source": "Local Parts Registry",
                    }
                ]
            }

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)
    monkeypatch.setattr(sequence_tools, "LocalRegistryVerificationAdapter", lambda: _FakeAdapter())

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert "Top hit summary" in output
    assert "Top hits table" in output
    assert "exact_match" in output
    assert "DATAFRAME_RENDERED" in output
    assert recorder.dataframe_calls == 1


def test_run_verification_displays_local_no_hit_message(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _NoHitAdapter:
        name = "local-parts-registry"

        def verify(self, sequence: str, database_label: str) -> dict:
            return {"status": "no_hits", "hits": []}

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)
    monkeypatch.setattr(sequence_tools, "LocalRegistryVerificationAdapter", lambda: _NoHitAdapter())

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert sequence_tools.SEQUENCE_TOOLS_LOCAL_NO_HIT_MESSAGE in output
    assert sequence_tools.SEQUENCE_TOOLS_BLAST_NO_HIT_MESSAGE not in output
    assert "NO_HITS" in output
    assert recorder.dataframe_calls == 0


def test_pasted_blast_tsv_renders_top_hits_table(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.selectbox_values[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY] = "Imported BLAST TSV"
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY] = (
        "query1\tBLAST123\t99.5\t96\t0\t0\t1\t96\t10\t105\t1e-40\t200\n"
    )
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert "Imported BLAST TSV" in output
    assert "Top hit summary" in output
    assert "Top hits table" in output
    assert "blast_hit" in output
    assert "DATAFRAME_RENDERED" in output
    assert recorder.dataframe_calls == 1


def test_empty_blast_tsv_renders_blast_specific_no_hit_message(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.selectbox_values[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY] = "Imported BLAST TSV"
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY] = "  \n"
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert sequence_tools.SEQUENCE_TOOLS_BLAST_NO_HIT_MESSAGE in output
    assert sequence_tools.SEQUENCE_TOOLS_LOCAL_NO_HIT_MESSAGE not in output
    assert "NO_HITS" in output
    assert "ready" not in output.lower()
    assert "approved" not in output.lower()
    assert "certified" not in output.lower()
    assert "Disclaimer:" in output
    assert recorder.dataframe_calls == 0


def test_header_only_blast_tsv_renders_blast_specific_no_hit_message(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.selectbox_values[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY] = "Imported BLAST TSV"
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY] = (
        "qseqid\tsseqid\tpident\tlength\tmismatch\tgapopen\tqstart\tqend\tsstart\tsend\tevalue\tbitscore\n"
    )
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert sequence_tools.SEQUENCE_TOOLS_BLAST_NO_HIT_MESSAGE in output
    assert sequence_tools.SEQUENCE_TOOLS_LOCAL_NO_HIT_MESSAGE not in output
    assert "Disclaimer:" in output


def test_malformed_blast_tsv_does_not_crash(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.selectbox_values[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY] = "Imported BLAST TSV"
    recorder.session_state[sequence_tools.SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY] = "not\ta\tblast\trow"
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert sequence_tools.SEQUENCE_TOOLS_UNAVAILABLE_MESSAGE in output
    assert "No external lookup was attempted" in output
    assert recorder.dataframe_calls == 0


def test_placeholder_source_remains_available(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.selectbox_values[sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY] = "Placeholder adapter"
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined()
    assert "Placeholder verification adapter" in output
    assert "REMOTE_UNAVAILABLE" in output
    assert sequence_tools.SEQUENCE_TOOLS_UNAVAILABLE_MESSAGE in output


def test_verification_ui_does_not_expose_agent_or_apply_controls(monkeypatch):
    import views.SequenceTools as sequence_tools

    recorder = _Recorder()
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_verification_panel(VALID_SEQ)

    output = recorder.joined().lower()
    assert "agent" not in output
    assert "auto-design" not in output
    assert "apply recommendation" not in output
    assert "validate" not in output
    assert "approve" not in output


def test_verification_panel_does_not_mutate_design_session_or_call_save_advance(monkeypatch):
    import views.SequenceTools as sequence_tools
    from core.design_session import DesignSession
    from core.session_keys import SK

    ds = DesignSession(
        step=5,
        gene_name="DemoGene",
        original_seq=VALID_SEQ,
        optimized_seq="ATGGCCGCTTAA",
        frame={"success": True, "sequence": VALID_SEQ + VALID_SEQ},
        primers=[{"name": "p1", "status": "Not Recommended"}],
        validation_results=[{"severity": "warning", "code": "existing"}],
    )
    ds_before = repr(ds)

    recorder = _Recorder()
    recorder.button_map["seq_tools_run_verification"] = True
    recorder.session_state[SK.DESIGN_SESSION] = ds
    fake_st = _FakeStreamlit(recorder)
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    class _Controller:
        save_calls = 0
        advance_calls = 0

        def save(self, _ds):
            self.save_calls += 1

        def advance(self):
            self.advance_calls += 1

    ctrl = _Controller()
    sequence_tools._render_verification_panel(VALID_SEQ)

    assert repr(recorder.session_state[SK.DESIGN_SESSION]) == ds_before
    assert ctrl.save_calls == 0
    assert ctrl.advance_calls == 0


def test_existing_send_to_wizard_gate_remains_ready_only():
    import views.SequenceTools as sequence_tools

    ready_result = sequence_tools.inspect_sequence(VALID_SEQ)
    review_result = sequence_tools.inspect_sequence("ATG" + "GCGCGC" * 6 + "TAA")

    assert sequence_tools._can_send_to_wizard(ready_result, ready_result.sequence) is True
    assert sequence_tools._can_send_to_wizard(review_result, review_result.sequence) is False
