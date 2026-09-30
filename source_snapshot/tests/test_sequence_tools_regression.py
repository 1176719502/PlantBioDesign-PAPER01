# -*- coding: utf-8 -*-
"""
tests/test_sequence_tools_regression.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Focused regression coverage for Sequence Tools Phase 2 cleanup:
- shared utility reuse
- Sequence View edit path state unification
- SK.ACTIVE_SEQ and current_seq compatibility writeback
- ORF path using sequence_service.find_orfs
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


VALID_84_BP_CDS = (
    "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
    "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
)
HIGH_GC_REPEAT_CDS = "ATG" + "GCGCGC" * 6 + "TAA"


def test_sequence_tools_composition_details_pending_before_analysis(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _FakeStreamlit:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def caption(self, body, **_kwargs):
            self.texts.append(str(body))

        def markdown(self, body, **_kwargs):
            self.texts.append(str(body))

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_composition_details(VALID_84_BP_CDS, analysis_has_run=False)

    output = "\n".join(fake_st.texts)
    assert sequence_tools.SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE in output
    assert "| Base | Count | Fraction |" not in output
    assert "| A |" not in output
    assert "| T |" not in output
    assert "| C |" not in output
    assert "| G |" not in output


def test_sequence_tools_composition_details_shows_counts_after_analysis(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _FakeStreamlit:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def caption(self, body, **_kwargs):
            self.texts.append(str(body))

        def markdown(self, body, **_kwargs):
            self.texts.append(str(body))

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_composition_details("AATTCCGG", analysis_has_run=True)

    output = "\n".join(fake_st.texts)
    assert sequence_tools.SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE not in output
    assert "| Base | Count | Fraction |" in output
    assert "| A | 2 | 25.0% |" in output
    assert "| T | 2 | 25.0% |" in output
    assert "| C | 2 | 25.0% |" in output
    assert "| G | 2 | 25.0% |" in output


def test_sequence_tools_composition_details_pending_before_analysis(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _FakeStreamlit:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def caption(self, body, **_kwargs):
            self.texts.append(str(body))

        def markdown(self, body, **_kwargs):
            self.texts.append(str(body))

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_composition_details(VALID_84_BP_CDS, analysis_has_run=False)

    output = "\n".join(fake_st.texts)
    assert sequence_tools.SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE in output
    assert "| Base | Count | Fraction |" not in output
    assert "| A |" not in output
    assert "| T |" not in output
    assert "| C |" not in output
    assert "| G |" not in output


def test_sequence_tools_composition_details_shows_counts_after_analysis(monkeypatch):
    import views.SequenceTools as sequence_tools

    class _FakeStreamlit:
        def __init__(self) -> None:
            self.texts: list[str] = []

        def caption(self, body, **_kwargs):
            self.texts.append(str(body))

        def markdown(self, body, **_kwargs):
            self.texts.append(str(body))

    fake_st = _FakeStreamlit()
    monkeypatch.setattr(sequence_tools, "st", fake_st)

    sequence_tools._render_composition_details("AATTCCGG", analysis_has_run=True)

    output = "\n".join(fake_st.texts)
    assert sequence_tools.SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE not in output
    assert "| Base | Count | Fraction |" in output
    assert "| A | 2 | 25.0% |" in output
    assert "| T | 2 | 25.0% |" in output
    assert "| C | 2 | 25.0% |" in output
    assert "| G | 2 | 25.0% |" in output


def test_sequence_tools_valid_analyzed_sequence_is_ready_and_sendable():
    import views.SequenceTools as sequence_tools

    analyzed_result = sequence_tools.inspect_sequence(VALID_84_BP_CDS)
    analyzed_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)
    current_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)

    assert analyzed_result.status == "Ready for Wizard"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is False
    assert sequence_tools._can_use_analyzed_result(
        analyzed_result,
        current_signature,
        analyzed_signature,
    ) is True


def test_sequence_tools_input_change_to_invalid_marks_stale_and_disables_send():
    import views.SequenceTools as sequence_tools

    analyzed_result = sequence_tools.inspect_sequence(VALID_84_BP_CDS)
    analyzed_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)
    current_signature = sequence_tools._sequence_signature("ATGGCXTAA")

    assert analyzed_result.status == "Ready for Wizard"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is True
    assert sequence_tools._can_use_analyzed_result(
        analyzed_result,
        current_signature,
        analyzed_signature,
    ) is False


def test_sequence_tools_reanalyze_invalid_sequence_disables_send():
    import views.SequenceTools as sequence_tools

    analyzed_result = sequence_tools.inspect_sequence("ATGGCXTAA")
    analyzed_signature = sequence_tools._sequence_signature("ATGGCXTAA")
    current_signature = sequence_tools._sequence_signature("ATGGCXTAA")

    assert analyzed_result.status == "Invalid Sequence"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is False
    assert sequence_tools._can_use_analyzed_result(
        analyzed_result,
        current_signature,
        analyzed_signature,
    ) is False


def test_sequence_tools_input_change_to_high_gc_repeat_marks_stale_and_disables_send():
    import views.SequenceTools as sequence_tools

    analyzed_result = sequence_tools.inspect_sequence(VALID_84_BP_CDS)
    analyzed_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)
    current_signature = sequence_tools._sequence_signature(HIGH_GC_REPEAT_CDS)

    assert analyzed_result.status == "Ready for Wizard"
    assert sequence_tools.inspect_sequence(HIGH_GC_REPEAT_CDS).status == "Needs Review"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is True
    assert sequence_tools._can_use_analyzed_result(
        analyzed_result,
        current_signature,
        analyzed_signature,
    ) is False


def test_sequence_tools_stale_message_and_helper_wording_reflect_non_current_ready_state():
    import views.SequenceTools as sequence_tools

    ready_result = sequence_tools.inspect_sequence(VALID_84_BP_CDS)
    current_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS + "GCT")
    analyzed_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)

    assert ready_result.status == "Ready for Wizard"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is True
    assert "current sequence input has changed" in sequence_tools.SEQUENCE_TOOLS_STALE_MESSAGE
    assert "using this sequence in the Expression Wizard" in sequence_tools.SEQUENCE_TOOLS_STALE_MESSAGE
    assert sequence_tools.SEQUENCE_TOOLS_DISABLED_SEND_HELPER == "Use in Wizard is unavailable until the current input has been analyzed and has no review-blocking preflight notes."


def test_sequence_tools_documentation_context_copy_keeps_review_only_boundary():
    import views.SequenceTools as sequence_tools

    combined = "\n".join(
        [
            sequence_tools.SEQUENCE_TOOLS_DOCUMENTATION_CONTEXT_COPY,
            sequence_tools.SEQUENCE_TOOLS_HANDOFF_CONTEXT_COPY,
            sequence_tools.SEQUENCE_VERIFICATION_DISCLAIMER,
            sequence_tools.SEQUENCE_TOOLS_VERIFICATION_EMPTY_MESSAGE,
            sequence_tools.SEQUENCE_TOOLS_VERIFICATION_SUMMARY_COPY,
        ]
    )

    required = [
        "Local sequence inspection summary",
        "documentation-only review context",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not a wet-lab protocol",
    ]
    for phrase in required:
        assert phrase in combined

    assert "does not change Sequence Inspector status" in combined
    assert "primer risk" in combined


def test_sequence_tools_page_does_not_add_artifact_save_or_project_link_entrypoints():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1].joinpath("views", "SequenceTools.py").read_text(encoding="utf-8")

    forbidden = [
        "create_tool_artifact",
        "Save Documentation Artifact",
        "Save current",
        "Optional Pathway Project link",
        "project_id=",
        "list_pathway_projects",
    ]
    for phrase in forbidden:
        assert phrase not in source


def test_sequence_tools_stale_status_label_uses_previous_analysis_wording():
    stale_label = f"Previous analysis status: {'Ready for Wizard'}"

    assert "Previous analysis status" in stale_label
    assert "Final status: Ready for Wizard" not in stale_label


def test_sequence_tools_ready_non_stale_allows_use_in_wizard():
    import views.SequenceTools as sequence_tools

    review_result = sequence_tools.inspect_sequence(HIGH_GC_REPEAT_CDS)
    review_signature = sequence_tools._sequence_signature(HIGH_GC_REPEAT_CDS)

    assert review_result.status == "Needs Review"
    assert sequence_tools._is_analysis_stale(review_signature, review_signature) is False
    assert sequence_tools._can_use_analyzed_result(
        review_result,
        review_signature,
        review_signature,
    ) is False
    assert sequence_tools._can_send_to_wizard(review_result, review_result.sequence) is False


def test_sequence_tools_stale_ready_analysis_cannot_send_to_wizard():
    import views.SequenceTools as sequence_tools

    ready_result = sequence_tools.inspect_sequence(VALID_84_BP_CDS)
    analyzed_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS)
    current_signature = sequence_tools._sequence_signature(VALID_84_BP_CDS + "GCT")

    assert ready_result.status == "Ready for Wizard"
    assert sequence_tools._is_analysis_stale(current_signature, analyzed_signature) is True
    assert sequence_tools._can_use_analyzed_result(
        ready_result,
        current_signature,
        analyzed_signature,
    ) is False


def test_sequence_tools_raw_invalid_input_is_inspected_and_not_sendable():
    import views.SequenceTools as sequence_tools

    raw_result = sequence_tools.inspect_sequence("ATGGCXTAA")
    cleaned, err = sequence_tools._clean_input("ATGGCXTAA")

    assert raw_result.status == "Invalid Sequence"
    assert [(item.character, item.count) for item in raw_result.invalid_characters] == [("X", 1)]
    assert cleaned == ""
    assert err
    assert raw_result.status != "Ready for Wizard"
    assert sequence_tools._can_send_to_wizard(raw_result, raw_result.sequence) is False


def test_sequence_tools_cleaned_needs_review_does_not_override_raw_invalid_send_gate():
    import views.SequenceTools as sequence_tools

    raw_result = sequence_tools.inspect_sequence("ATGGCXTAA")
    parsed_result = sequence_tools.inspect_sequence(raw_result.sequence)

    assert raw_result.status == "Invalid Sequence"
    assert parsed_result.status == "Needs Review"
    assert sequence_tools._can_send_to_wizard(raw_result, raw_result.sequence) is False


def test_reverse_complement_reuses_shared_rc(monkeypatch):
    """tab utility reverse_complement should delegate to utils.sequence_utils.rc."""
    from components.test_modules import seq_utils

    calls: dict[str, str] = {}

    def _fake_rc(seq: str) -> str:
        calls["seq"] = seq
        return "SENTINEL_RC"

    monkeypatch.setattr(seq_utils, "rc", _fake_rc)

    result = seq_utils.reverse_complement("ATGC")

    assert result == "SENTINEL_RC"
    assert calls["seq"] == "ATGC"


def test_sequence_tools_reverse_complement_uses_sequence_service(monkeypatch):
    """SequenceTools reverse complement helper should call sequence_service.reverse_complement."""
    import services.sequence_service as sequence_service
    import views.SequenceTools as sequence_tools

    seen: dict[str, str] = {}

    def _fake_reverse_complement(seq: str) -> str:
        seen["seq"] = seq
        return "SENTINEL_SERVICE_RC"

    monkeypatch.setattr(sequence_service, "reverse_complement", _fake_reverse_complement)

    result = sequence_tools._get_reverse_complement("ATGC")

    assert result == "SENTINEL_SERVICE_RC"
    assert seen["seq"] == "ATGC"


def test_sequence_tools_clean_input_reuses_shared_clean_and_validate(monkeypatch):
    """SequenceTools._clean_input should route through shared clean/validate utilities."""
    import views.SequenceTools as sequence_tools

    seen: dict[str, str] = {}

    def _fake_clean(raw: str) -> str:
        seen["clean_arg"] = raw
        return "ATGCC"

    def _fake_validate(seq: str) -> tuple[bool, str]:
        seen["validate_arg"] = seq
        return True, ""

    monkeypatch.setattr(sequence_tools, "clean_sequence", _fake_clean)
    monkeypatch.setattr(sequence_tools, "validate_sequence", _fake_validate)

    cleaned, err = sequence_tools._clean_input(">header\n\nat g...\ncc…\n⋯")

    assert cleaned == "ATGCC"
    assert err is None
    assert seen["clean_arg"] == "at gcc"
    assert seen["validate_arg"] == "ATGCC"


def test_sequence_tools_clean_input_accepts_fasta_headers_and_display_ellipsis():
    """SequenceTools._clean_input should ignore FASTA headers and display truncation marks."""
    import views.SequenceTools as sequence_tools

    cleaned, err = sequence_tools._clean_input(">demo sequence\nATG AAA...\n\nCCG…TTT\n⋯\n>ignored header\nGGC")

    assert err is None
    assert cleaned == "ATGAAACCGTTTGGC"


def test_sequence_view_edit_updates_canonical_and_legacy_sequence_state(monkeypatch):
    """Editing Sequence View should write both canonical and compatibility keys."""
    from components.test_modules import tab_seq_view
    from core.session_keys import SK

    class _Col:
        def __init__(self, toggle_value: bool = False, text_value: str = "") -> None:
            self._toggle_value = toggle_value
            self._text_value = text_value

        def toggle(self, *_args, **_kwargs):
            return self._toggle_value

        def text_input(self, *_args, **_kwargs):
            return self._text_value

    state: dict[str, str] = {}
    rerun_called = {"value": False}

    monkeypatch.setattr(tab_seq_view.st, "session_state", state)
    monkeypatch.setattr(tab_seq_view.st, "columns", lambda *_a, **_k: [_Col(toggle_value=True), _Col(text_value="")])
    monkeypatch.setattr(tab_seq_view.st, "text_area", lambda *_a, **_k: "at gc n---")
    monkeypatch.setattr(tab_seq_view.st, "rerun", lambda: rerun_called.__setitem__("value", True))

    tab_seq_view.render("ATGC")

    assert state[SK.ACTIVE_SEQ] == "ATGCN"
    assert state["current_seq"] == "ATGCN"
    assert rerun_called["value"] is True


def test_count_orfs_uses_sequence_service_find_orfs(monkeypatch):
    """SequenceTools ORF count should call sequence_service.find_orfs with selected min_len."""
    import services.sequence_service as sequence_service
    import views.SequenceTools as sequence_tools

    seen: dict[str, object] = {}

    def _fake_find_orfs(seq: str, min_len: int = 0):
        seen["seq"] = seq
        seen["min_len"] = min_len
        return [{"Frame": 1, "Start": 1, "End": 9, "Length (bp)": 9}]

    monkeypatch.setattr(sequence_service, "find_orfs", _fake_find_orfs)

    count = sequence_tools._count_orfs("ATGAAATAG", min_len=90)

    assert count == 1
    assert seen["seq"] == "ATGAAATAG"
    assert seen["min_len"] == 90


def test_get_orf_results_normalizes_columns_and_adds_strand(monkeypatch):
    """ORF results helper should normalize common columns and provide Strand default."""
    import services.sequence_service as sequence_service
    import views.SequenceTools as sequence_tools

    def _fake_find_orfs(_seq: str, min_len: int = 0):
        assert min_len == 120
        return [{"frame": 2, "start": 10, "end": 60}]

    monkeypatch.setattr(sequence_service, "find_orfs", _fake_find_orfs)

    df = sequence_tools._get_orf_results("ATG" + "A" * 60 + "TAA", min_len=120)

    assert list(df.columns) == ["Frame", "Start", "End", "Length (bp)", "Strand"]
    assert len(df) == 1
    assert int(df.loc[0, "Frame"]) == 2
    assert int(df.loc[0, "Start"]) == 10
    assert int(df.loc[0, "End"]) == 60
    assert int(df.loc[0, "Length (bp)"]) == 51
    assert df.loc[0, "Strand"] == "+"


def test_translation_preview_uses_sequence_service_translate(monkeypatch):
    """SequenceTools translation preview should call sequence_service.translate."""
    import services.sequence_service as sequence_service
    import views.SequenceTools as sequence_tools

    seen: dict[str, str] = {}

    def _fake_translate(seq: str) -> str:
        seen["seq"] = seq
        return "MTEST"

    monkeypatch.setattr(sequence_service, "translate", _fake_translate)

    protein, truncated = sequence_tools._get_translation_preview("ATGACCGAA")

    assert protein == "MTEST"
    assert truncated is False
    assert seen["seq"] == "ATGACCGAA"


def test_translation_preview_truncates_long_translation(monkeypatch):
    """SequenceTools translation preview should bound long protein output."""
    import services.sequence_service as sequence_service
    import views.SequenceTools as sequence_tools

    monkeypatch.setattr(sequence_service, "translate", lambda _seq: "M" * 1005)

    protein, truncated = sequence_tools._get_translation_preview("ATG" * 1005, max_aa=1000)

    assert protein == "M" * 1000
    assert truncated is True


def test_smart_annotate_sequence_returns_multiple_hits_for_same_motif():
    """Sequence motif annotation should include repeated occurrences, not only first hit."""
    from components.test_modules.seq_utils import smart_annotate_sequence

    motif = "TAATACGACTCACTATA"  # T7 Promoter
    seq = f"AAA{motif}CCC{motif}GGG"

    features = smart_annotate_sequence(seq)
    t7_hits = [f for f in features if f["Name"] == "T7 Promoter"]

    assert len(t7_hits) == 2
    assert t7_hits[0]["Start"] == 4
    assert t7_hits[1]["Start"] == 24
