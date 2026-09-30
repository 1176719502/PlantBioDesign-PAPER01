from __future__ import annotations

import json
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.design_session import DesignSession
from services.pathway_wizard_context import (
    PATHWAY_WIZARD_CONTEXT_KEY,
    build_pathway_design_snapshot,
    build_pathway_validation_summary,
    build_pathway_wizard_context,
    can_launch_expression_design,
    clear_pathway_context_for_independent_wizard_entry,
    create_design_session_from_pathway_step,
    link_saved_design_to_active_pathway_context,
    normalize_gene_sequence,
)


def _step(**overrides):
    data = {
        "id": 12,
        "project_id": 3,
        "step_order": 2,
        "step_name": "Precursor activation",
        "reaction_name": "Activation reaction",
        "gene_name": "demo_gene",
        "gene_sequence": "atg aaa ttt taa",
    }
    data.update(overrides)
    return data


def test_can_launch_expression_design_requires_gene_name_and_sequence():
    assert can_launch_expression_design(_step()) is True
    assert can_launch_expression_design(_step(gene_name="")) is False
    assert can_launch_expression_design(_step(gene_sequence="")) is False
    assert can_launch_expression_design(_step(gene_name="  ", gene_sequence="ATG")) is False
    assert can_launch_expression_design(_step(gene_name="Gene", gene_sequence="  \n  ")) is False
    assert can_launch_expression_design(None) is False


def test_normalize_gene_sequence_uppercases_and_removes_whitespace():
    assert normalize_gene_sequence("atg aaa\nccc\ttaa") == "ATGAAACCCTAA"


def test_create_design_session_from_pathway_step_prefills_only_step1_fields():
    ds = create_design_session_from_pathway_step(_step())

    assert isinstance(ds, DesignSession)
    assert ds.step == 1
    assert ds.gene_name == "demo_gene"
    assert ds.original_seq == "ATGAAATTTTAA"

    assert ds.host == ""
    assert ds.tag == ""
    assert ds.elements == {}
    assert ds.optimized_seq == ""
    assert ds.frame == {}
    assert ds.codon_report == {}
    assert ds.cloning_method == ""
    assert ds.primers == []
    assert ds.validation_results == []
    assert ds.primer_context_host == ""
    assert ds.primer_context_seq_hash == ""
    assert ds.frame_context_signature == ""
    assert ds.primer_context_signature == ""
    assert ds.validation_context_signature == ""



def test_build_pathway_wizard_context_captures_pathway_origin_without_sequence_payload():
    project = {"id": 3, "name": "Flavonoid Pathway"}
    context = build_pathway_wizard_context(project, _step())

    assert context["source"] == "pathway_workspace"
    assert context["project_id"] == 3
    assert context["project_name"] == "Flavonoid Pathway"
    assert context["step_id"] == 12
    assert context["step_order"] == 2
    assert context["step_name"] == "Precursor activation"
    assert context["reaction_name"] == "Activation reaction"
    assert context["gene_name"] == "demo_gene"
    assert context["gene_sequence_hash"]
    assert "gene_sequence" not in context
    assert context["status"] == "active"


def _complete_ds() -> DesignSession:
    return DesignSession(
        step=6,
        gene_name="demo_gene",
        original_seq="ATG" + "AAA" * 20 + "TAA",
        optimized_seq="ATG" + "GCC" * 20 + "TAA",
        host="E.coli BL21(DE3)",
        tag="His6-tag",
        elements={
            "promoter_name": "T7 promoter",
            "rbs_name": "B0034 RBS",
            "terminator_name": "T7 terminator",
        },
        frame={
            "success": True,
            "final_sequence": "AAA" + "ATG" + "GCC" * 20 + "TAA" + "TTT",
            "total_length": 72,
            "vector_suggestion": "pET-style vector",
        },
        primers=[
            {
                "Fragment Name": "Expression frame",
                "Quality Grade": "Not Recommended",
                "Quality Reasons": ["Severe primer interaction risk"],
            }
        ],
        validation_results=[
            {"severity": "warning", "code": "PRIMER_HIGH_RISK", "title": "High-risk primer pairs detected"},
            {"severity": "critical", "code": "STOP_CODON", "title": "Blocking issue"},
        ],
    )


def test_build_pathway_design_snapshot_uses_lengths_and_hashes_without_raw_sequences():
    snapshot = build_pathway_design_snapshot(
        _complete_ds(),
        saved_design_name="Saved Demo Design",
        validation_state={"status": "completed_blocked"},
        created_at="2026-05-21T12:00:00",
    )

    assert snapshot["saved_design_name"] == "Saved Demo Design"
    assert snapshot["gene_name"] == "demo_gene"
    assert snapshot["host"] == "E.coli BL21(DE3)"
    assert snapshot["selected_elements"]["promoter_name"] == "T7 promoter"
    assert snapshot["optimized_seq_length_bp"] > 0
    assert snapshot["optimized_seq_hash"]
    assert snapshot["expression_frame_length_bp"] > 0
    assert snapshot["expression_frame_hash"]
    assert snapshot["primer_count"] == 1
    assert snapshot["validation_status"] == "completed_blocked"
    assert snapshot["linked_is_experimental_ready"] is False
    serialized = json.dumps(snapshot)
    assert "ATGGCCGCCGCC" not in serialized
    assert "final_sequence" not in serialized


def test_build_pathway_validation_summary_preserves_not_recommended_risk_semantics():
    summary = build_pathway_validation_summary(
        _complete_ds(),
        validation_state={
            "status": "completed_blocked",
            "is_complete": True,
            "is_stale": False,
            "warning_count": 1,
            "critical_count": 1,
        },
        export_recommendation={
            "recommendation": "Review blocked by unresolved risk signals",
            "conclusion": "Primer risks remain.",
            "action": "Resolve primer risks before opening the supporting assembly preview workspace.",
            "primer_high_risk_count": 1,
            "primer_review_count": 0,
            "primer_action_required_count": 1,
            "affected_fragments": ["Expression frame"],
        },
        documentation_only_export=True,
    )

    assert summary["validation_status"] == "completed_blocked"
    assert len(summary["validation_warnings"]) == 1
    assert len(summary["blocking_issues"]) == 1
    assert summary["primer_risk_status"] == "not_recommended"
    assert summary["export_recommendation"] == "Review blocked by unresolved risk signals"
    assert summary["documentation_only"] is True
    assert summary["not_recommended_for_experimental_use"] is False
    assert summary["linked_is_experimental_ready"] is False


def test_link_saved_design_skips_when_no_active_context(monkeypatch):
    session_state = {}
    fake_st = types.SimpleNamespace(session_state=session_state)
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    ok, message, attempted = link_saved_design_to_active_pathway_context(
        _complete_ds(),
        saved_design_name="Saved Demo Design",
    )

    assert ok is True
    assert attempted is False
    assert "No active pathway context" in message


def test_clear_pathway_context_for_independent_entry_clears_any_pathway_context_status(monkeypatch):
    for status in ["active", "linked", "stale"]:
        session_state = {
            PATHWAY_WIZARD_CONTEXT_KEY: {
                "source": "pathway_workspace",
                "status": status,
                "project_id": 3,
                "step_id": 12,
            }
        }
        fake_st = types.SimpleNamespace(session_state=session_state)
        monkeypatch.setitem(sys.modules, "streamlit", fake_st)

        clear_pathway_context_for_independent_wizard_entry()

        assert PATHWAY_WIZARD_CONTEXT_KEY not in session_state


def test_link_saved_design_marks_context_linked_on_success(monkeypatch):
    context = build_pathway_wizard_context({"id": 3, "name": "Pathway"}, _step())
    session_state = {PATHWAY_WIZARD_CONTEXT_KEY: context}
    fake_st = types.SimpleNamespace(session_state=session_state)
    calls = []

    def fake_link_expression_design_to_step(**kwargs):
        calls.append(kwargs)
        return True, "Linked.", 9

    fake_repo = types.SimpleNamespace(
        link_expression_design_to_step=fake_link_expression_design_to_step,
        safe_json_dumps=lambda payload: json.dumps(payload, default=str),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "services.pathway_repository", fake_repo)

    ok, message, attempted = link_saved_design_to_active_pathway_context(
        _complete_ds(),
        saved_design_name="Saved Demo Design",
        validation_state={"status": "completed_review"},
        export_recommendation={"recommendation": "Export with Review Required"},
        documentation_only_export=True,
    )

    assert ok is True
    assert message == "Linked."
    assert attempted is True
    assert calls
    assert calls[0]["project_id"] == 3
    assert calls[0]["step_id"] == 12
    assert calls[0]["design_name"] == "Saved Demo Design"
    linked_context = session_state[PATHWAY_WIZARD_CONTEXT_KEY]
    assert linked_context["status"] == "linked"
    assert linked_context["linked_design_name"] == "Saved Demo Design"
    assert linked_context["linked_at"]


def test_link_saved_design_keeps_context_on_link_failure(monkeypatch):
    context = build_pathway_wizard_context({"id": 3, "name": "Pathway"}, _step())
    session_state = {PATHWAY_WIZARD_CONTEXT_KEY: context}
    fake_st = types.SimpleNamespace(session_state=session_state)

    fake_repo = types.SimpleNamespace(
        link_expression_design_to_step=lambda **kwargs: (False, "Link failed.", None),
        safe_json_dumps=lambda payload: json.dumps(payload, default=str),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "services.pathway_repository", fake_repo)

    ok, message, attempted = link_saved_design_to_active_pathway_context(
        _complete_ds(),
        saved_design_name="Saved Demo Design",
    )

    assert ok is False
    assert message == "Link failed."
    assert attempted is True
    assert session_state[PATHWAY_WIZARD_CONTEXT_KEY] == context
