from __future__ import annotations

import importlib
import inspect
import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_bottleneck_service import analyze_pathway_bottlenecks
from services.pathway_completeness_service import build_pathway_completeness

FORBIDDEN = (
    "This is the bottleneck",
    "Bottleneck identified",
    "Yield will improve",
    "Predicted production",
    "Predicted yield",
    "Automatically optimized pathway",
    "Ready for Experimental Use",
    "Experimental Ready",
    "Recommended optimization",
)


def _step(step_id: int = 1, sequence: str = "ATGAAATAA") -> dict:
    return {
        "id": step_id,
        "step_order": step_id,
        "step_name": f"Step {step_id}",
        "substrate": "Precursor",
        "product": "Product",
        "enzyme_name": "Enz",
        "gene_name": "gene",
        "gene_sequence": sequence,
    }


def _signals_by_type(signals: list[dict], signal_type: str) -> list[dict]:
    return [signal for signal in signals if signal["signal_type"] == signal_type]


def _all_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)
    elif isinstance(value, str):
        yield value


def test_output_schema_completeness():
    signals = analyze_pathway_bottlenecks({"pathway_steps": [_step()], "project_test_records": []})

    assert signals
    required = {"signal_type", "priority", "scope", "related_step_id", "evidence", "message", "suggested_next_check", "boundary_note"}
    for signal in signals:
        assert required == set(signal)
        assert signal["priority"] in {"high_review", "medium_review", "low_review", "info"}
        assert signal["scope"] in {"project-level", "step-level"}
        assert signal["boundary_note"]


def test_missing_expression_design_signal():
    signals = analyze_pathway_bottlenecks({"pathway_steps": [_step()], "project_test_records": [{"id": 1}]})

    missing = _signals_by_type(signals, "missing_expression_design")
    assert len(missing) == 1
    assert missing[0]["priority"] == "medium_review"
    assert missing[0]["scope"] == "step-level"
    assert missing[0]["related_step_id"] == 1


def test_validation_warning_signal_is_medium_review():
    signals = analyze_pathway_bottlenecks({
        "pathway_steps": [_step()],
        "expression_design_links": [{
            "step_id": 1,
            "design_id": 10,
            "validation_summary_json": {"warnings": ["Review recorded validation warning."]},
        }],
        "project_test_records": [{"id": 1}],
    })

    risk = _signals_by_type(signals, "linked_design_validation_risk")
    assert len(risk) == 1
    assert risk[0]["priority"] == "medium_review"
    assert risk[0]["evidence"]["warning_count"] == 1


def test_blocking_issue_high_risk_and_not_recommended_are_high_review():
    cases = [
        {"blocking_issues": ["Blocking issue"]},
        {"primer_risk": "high-risk primer"},
        {"not_recommended_for_experimental_use": True},
    ]
    for summary in cases:
        signals = analyze_pathway_bottlenecks({
            "pathway_steps": [_step()],
            "expression_design_links": [{"step_id": 1, "design_id": 10, "validation_summary_json": summary}],
            "project_test_records": [{"id": 1}],
        })
        risk = _signals_by_type(signals, "linked_design_validation_risk")
        assert len(risk) == 1
        assert risk[0]["priority"] == "high_review"


def test_intermediate_high_and_product_low_signal():
    signals = analyze_pathway_bottlenecks({
        "pathway_steps": [_step()],
        "expression_design_links": [{"step_id": 1, "design_id": 10}],
        "project_test_records": [{"id": 7, "titer": 0.1, "intermediate_accumulation": 0.9, "condition": "Test condition"}],
    })

    pattern = _signals_by_type(signals, "product_low_intermediate_high")
    assert len(pattern) == 1
    assert pattern[0]["priority"] == "high_review"
    assert pattern[0]["scope"] == "project-level"


def test_poor_growth_signal_priority_mapping():
    signals = analyze_pathway_bottlenecks({
        "pathway_steps": [_step()],
        "expression_design_links": [{"step_id": 1, "design_id": 10}],
        "step_test_records": {1: [{"id": 8, "growth_status": "inhibited"}]},
    })

    growth = _signals_by_type(signals, "poor_growth_recorded")
    assert len(growth) == 1
    assert growth[0]["priority"] == "high_review"
    assert growth[0]["scope"] == "step-level"


def test_missing_test_records_info_signal():
    signals = analyze_pathway_bottlenecks({"pathway_steps": [_step()], "expression_design_links": [{"step_id": 1, "design_id": 10}]})

    missing = _signals_by_type(signals, "missing_test_records")
    assert missing
    assert all(signal["priority"] == "info" for signal in missing)
    assert any("Missing records do not change pathway completeness score" in signal["boundary_note"] for signal in missing)


def test_incomplete_step_documentation_signal():
    signals = analyze_pathway_bottlenecks({
        "pathway_steps": [_step(sequence="")],
        "expression_design_links": [{"step_id": 1, "design_id": 10}],
        "project_test_records": [{"id": 1}],
        "pathway_completeness": {"score": 75, "step_summaries": [{"step_id": 1, "missing_items": ["Step 1 is missing gene sequence."]}]},
    })

    doc = _signals_by_type(signals, "incomplete_step_documentation")
    assert len(doc) == 1
    assert doc[0]["priority"] == "medium_review"
    assert doc[0]["evidence"]["sequence_present"] is False


def test_forbidden_wording_absent_from_all_generated_string_fields():
    signals = analyze_pathway_bottlenecks({
        "pathway_steps": [_step(sequence="")],
        "expression_design_links": [{"step_id": 1, "design_id": 10, "validation_summary_json": {"warnings": ["warning"]}}],
        "project_test_records": [{"id": 1, "titer": 0.1, "intermediate_accumulation": 0.9, "growth_status": "poor"}],
        "pathway_completeness": {"step_summaries": [{"step_id": 1, "missing_items": ["missing sequence"]}]},
    })

    generated_text = "\n".join(_all_strings(signals))
    for phrase in FORBIDDEN:
        assert phrase not in generated_text


def test_completeness_score_is_not_modified_or_recalculated_by_service():
    project = {"id": 1, "target_product": "Product"}
    steps = [_step()]
    links = [{"step_id": 1, "design_id": 10}]
    completeness = build_pathway_completeness(project, steps, links)
    before = deepcopy(completeness)

    analyze_pathway_bottlenecks({
        "pathway_steps": steps,
        "expression_design_links": links,
        "project_test_records": [],
        "pathway_completeness": completeness,
    })

    assert completeness == before
    assert completeness["score"] == 100


def test_service_has_no_forbidden_integration_imports_or_calls():
    module = importlib.import_module("services.pathway_bottleneck_service")
    source = inspect.getsource(module)

    forbidden_tokens = (
        "streamlit",
        "PathwayWorkspace",
        "PathwayProjects",
        "dashboard",
        "design_saver",
        "step6",
        "migration",
        "sqlite3",
        "requests",
        "sklearn",
        "tensorflow",
        "torch",
        "openai",
        "agent",
    )
    for token in forbidden_tokens:
        assert token not in source.lower()
