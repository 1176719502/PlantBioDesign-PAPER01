# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import plant_goal_route_generator as route_service
from services import plant_synbio_knowledge_base as kb_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("best ", "route"),
    _term("correct ", "route"),
    _term("valid", "ated"),
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("proto", "col"),
    _term("yield ", "pre", "diction"),
    _term("expression ", "pre", "diction"),
    _term("guaranteed expression"),
)


def _protein_case(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "case_id": "CASE-PROTEIN-001",
        "classification": "direct",
        "source_reference": {
            "source_id": "SRC-PROTEIN-001",
            "doi": "10.0000/protein",
            "title": "Plant protein expression evidence metadata",
            "year": "2025",
        },
        "plant_context": {
            "plant_species": "Oryza sativa",
            "tissue_context": "seed",
        },
        "target_context": {
            "target_trait_or_product": "albumin protein",
            "pathway": "",
        },
        "component_context": {
            "gene": "albumin CDS source note",
            "enzyme": "",
            "promoter": "seed promoter source note",
            "cds": "albumin CDS source note",
            "vector": "plant expression vector source note",
        },
        "missing_fields": ["marker"],
        "manual_review_required": True,
    }
    record.update(overrides)
    return record


def test_template_without_case_support_blocks_route_generation_with_gaps_and_tasks() -> None:
    intake = kb_service.build_plant_goal_evidence_intake("甘蔗 健康糖")
    result = route_service.generate_plant_candidate_route(
        "甘蔗 健康糖",
        intake["matched_goal_type"],
        intake["matched_route_templates"],
        [],
    )

    assert result["route_generation_status"] == route_service.ROUTE_GENERATION_BLOCKED
    assert result["manual_review_required"] is True
    assert result["candidate_route"] is None
    assert {
        "exact target metabolite",
        "pathway",
        "gene/enzyme",
        "tissue/context",
        "sugarcane or adjacent plant cases",
        "expression system evidence",
    } <= set(result["evidence_gaps"])
    assert result["discovery_tasks"]
    assert all(task["status"] == "manual_review_required" for task in result["discovery_tasks"])


def test_direct_evidence_case_allows_case_supported_candidate_route_draft() -> None:
    intake = kb_service.build_plant_goal_evidence_intake(
        "Plant protein expression review",
        {
            "target_product": "albumin protein",
            "gene_or_cds_source": "albumin CDS source note",
            "plant_context": "rice seed",
            "expression_compartment": "seed",
            "component_evidence_context": "source metadata",
            "case_evidence_context": "direct case metadata",
        },
    )
    result = route_service.generate_plant_candidate_route(
        "Plant protein expression review",
        intake["matched_goal_type"],
        intake["matched_route_templates"],
        [_protein_case()],
    )

    assert result["route_generation_status"] == route_service.ROUTE_GENERATION_ALLOWED
    candidate = result["candidate_route"]
    assert candidate is not None
    assert candidate["route_framing"] == "case-supported option"
    assert candidate["supporting_source_ids"] == ["SRC-PROTEIN-001"]
    assert candidate["supporting_case_ids"] == ["CASE-PROTEIN-001"]
    assert "target_product" in candidate["required_component_slots"]
    assert "gene_or_cds_source" in candidate["required_component_slots"]
    assert candidate["manual_review_required"] is True
    assert result["manual_review_required"] is True


def test_adjacent_case_support_is_allowed_but_missing_fields_are_preserved() -> None:
    intake = kb_service.build_plant_goal_evidence_intake(
        "Plant protein expression review",
        {
            "target_product": "albumin protein",
            "gene_or_cds_source": "albumin CDS source note",
            "plant_context": "rice seed",
            "expression_compartment": "seed",
            "component_evidence_context": "source metadata",
            "case_evidence_context": "adjacent case metadata",
        },
    )
    result = route_service.generate_plant_candidate_route(
        "Plant protein expression review",
        intake["matched_goal_type"],
        intake["matched_route_templates"],
        [_protein_case(classification="adjacent", missing_fields=["promoter", "vector"])],
    )

    candidate = result["candidate_route"]
    assert result["route_generation_status"] == route_service.ROUTE_GENERATION_ALLOWED
    assert candidate is not None
    assert {"promoter", "vector"} <= set(candidate["missing_fields"])
    assert any("Resolve missing fields" in item for item in candidate["manual_review_items"])


def test_route_generator_copy_avoids_unsafe_claims() -> None:
    result_text = str(
        route_service.generate_plant_candidate_route(
            "Plant protein expression review",
            {"goal_type_id": "plant_molecular_farming_protein_expression"},
            [
                {
                    "route_template_id": "protein-route",
                    "goal_type_id": "plant_molecular_farming_protein_expression",
                    "label": "Protein expression evidence route",
                    "required_inputs": ["target_product", "gene_or_cds_source"],
                    "evidence_needed": ["direct plant case evidence"],
                }
            ],
            [_protein_case()],
        )
    ).lower()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_goal_route_generator.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in result_text
        assert forbidden not in service_text


def test_route_generator_service_does_not_import_streamlit_or_network_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant route generator must stay offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = route_service.generate_plant_candidate_route(
        "Plant protein expression review",
        {"goal_type_id": "plant_molecular_farming_protein_expression"},
        [{"route_template_id": "protein-route", "goal_type_id": "plant_molecular_farming_protein_expression"}],
        [_protein_case()],
    )

    assert result["route_generation_status"] == route_service.ROUTE_GENERATION_ALLOWED
    importlib.reload(route_service)
