from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_completeness_service import build_pathway_completeness


def _project() -> dict:
    return {
        "id": 1,
        "name": "Naringenin Pathway",
        "target_product": "Naringenin",
        "host": "E. coli BL21(DE3)",
    }


def _complete_step() -> dict:
    return {
        "id": 10,
        "project_id": 1,
        "step_order": 1,
        "step_name": "Chalcone synthesis",
        "substrate": "p-Coumaroyl-CoA",
        "product": "Naringenin chalcone",
        "enzyme_name": "CHS",
        "gene_name": "chs",
        "gene_sequence": "ATGAAATAA",
    }


def test_no_steps_score_is_zero():
    summary = build_pathway_completeness(_project(), [], [])

    assert summary["score"] == 0
    assert summary["status"] == "Incomplete"
    assert "Pathway project has no pathway steps." in summary["missing_items"]
    assert summary["step_summaries"] == []


def test_missing_step_fields_are_reported():
    step = {
        "id": 10,
        "project_id": 1,
        "step_order": 1,
        "step_name": "Incomplete step",
        "substrate": "",
        "product": "",
        "enzyme_name": "",
        "gene_name": "",
        "gene_sequence": "",
    }

    summary = build_pathway_completeness(_project(), [step], [])

    assert summary["score"] == 0
    assert "Step 1 is missing substrate." in summary["missing_items"]
    assert "Step 1 is missing product." in summary["missing_items"]
    assert "Step 1 is missing enzyme." in summary["missing_items"]
    assert "Step 1 is missing gene." in summary["missing_items"]
    assert "Step 1 is missing gene sequence." in summary["missing_items"]
    assert "Step 1 has no linked expression design." in summary["missing_items"]


def test_complete_step_without_expression_design_scores_seventy_five():
    summary = build_pathway_completeness(_project(), [_complete_step()], [])

    assert summary["score"] == 75
    assert summary["status"] == "In Progress"
    assert summary["step_summaries"][0]["score"] == 75
    assert summary["step_summaries"][0]["has_expression_design"] is False
    assert summary["missing_items"] == ["Step 1 has no linked expression design."]


def test_linked_expression_design_scores_one_hundred():
    expression_links = [
        {
            "id": 100,
            "project_id": 1,
            "step_id": 10,
            "design_name": "Linked expression design",
        }
    ]

    summary = build_pathway_completeness(_project(), [_complete_step()], expression_links)

    assert summary["score"] == 100
    assert summary["status"] == "Mostly Complete"
    assert summary["missing_items"] == []
    assert summary["step_summaries"][0]["score"] == 100
    assert summary["step_summaries"][0]["has_expression_design"] is True
