from __future__ import annotations

import importlib
import inspect
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import target_design_router as router


def _combined_text(value) -> str:
    if isinstance(value, dict):
        return "\n".join(_combined_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_combined_text(item) for item in value)
    return str(value)


def test_hsa_routes_to_protein_or_secreted_construct_draft() -> None:
    draft = router.route_target_design(
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        expression_purpose="protein expression",
        route_hint="secreted protein",
        source_hint="local source note",
    )

    assert draft["target_class"] == "protein_expression"
    assert draft["design_route"] == "secreted_protein_expression"
    assert draft["construct_template"]["structure"] == [
        "promoter",
        "optional signal peptide",
        "HSA CDS",
        "terminator",
    ]
    assert draft["gene_slots"][0]["gene_label"] == "HSA"
    assert draft["cassette_slots"][0]["parts"][1]["part_role"] == "signal peptide"
    assert "HSA CDS source/provenance" in draft["source_requirements"]
    assert draft["support_status"] == "supported"


def test_generic_goi_in_plant_routes_to_single_goi_expression() -> None:
    draft = router.route_target_design(
        target_name="GOI",
        target_type="gene",
        host_category="plant",
        expression_purpose="expression design record",
        gene_list=["GOI"],
    )

    assert draft["target_class"] == "single_gene"
    assert draft["design_route"] == "single_goi_expression"
    assert draft["construct_template"]["structure"] == ["promoter", "CDS", "terminator"]
    assert draft["required_parts"] == [
        "host context documentation row",
        "promoter documentation row",
        "CDS documentation row",
        "terminator documentation row",
        "vector backbone documentation row",
    ]
    assert draft["gene_slots"][0]["gene_label"] == "GOI"
    assert draft["cassette_slots"][0]["parts"][1]["part_label"] == "GOI"
    assert draft["support_status"] == "needs_review"
    assert "specific_host" in draft["missing_fields"]


def test_artemisinin_precursor_routes_to_multi_gene_pathway_slots() -> None:
    draft = router.route_target_design(
        target_name="artemisinin precursor",
        target_type="pathway",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        route_hint="multi-gene pathway",
    )

    expected_genes = ["ADS", "CYP71AV1", "CPR", "ADH1", "DBR2", "ALDH1"]
    assert draft["target_class"] == "multi_gene_pathway"
    assert draft["design_route"] == "multi_gene_pathway_expression"
    assert [slot["gene_label"] for slot in draft["gene_slots"]] == expected_genes
    assert [slot["gene_label"] for slot in draft["cassette_slots"]] == expected_genes
    assert len(draft["cassette_slots"]) == len(expected_genes)
    assert all(
        [part["part_role"] for part in cassette["parts"]] == ["promoter", "CDS", "terminator"]
        for cassette in draft["cassette_slots"]
    )
    assert "promoter_choices" in draft["missing_fields"]
    assert "CDS_sources" in draft["missing_fields"]
    assert draft["support_status"] == "partially_supported"


def test_sugarcane_healthy_sugar_routes_to_clarification_without_cassettes() -> None:
    draft = router.route_target_design(
        target_name="sugarcane healthy sugar",
        target_type="trait",
        host_category="plant",
        specific_host="sugarcane",
    )

    assert draft["target_class"] == "trait_or_phenotype"
    assert draft["design_route"] == "needs_target_clarification"
    assert draft["gene_slots"] == []
    assert draft["cassette_slots"] == []
    assert draft["support_status"] == "unresolved"
    notes = "\n".join(draft["review_notes"])
    assert "sweet protein expression" in notes
    assert "rare sugar enzyme expression" in notes
    assert "steviol glycoside pathway" in notes
    assert "sugar metabolism modification" in notes
    assert "not construct-ready" in draft["boundary_note"]


def test_unknown_target_returns_unresolved_status() -> None:
    draft = router.route_target_design(target_name="mystery target")

    assert draft["target_class"] == "unresolved_target"
    assert draft["design_route"] == "needs_target_clarification"
    assert draft["support_status"] == "unresolved"
    assert draft["gene_slots"] == []
    assert draft["cassette_slots"] == []
    assert "target_type" in draft["missing_fields"]
    assert "design_route_clarification" in draft["missing_fields"]


def test_boundary_copy_does_not_contain_forbidden_claim_wording() -> None:
    drafts = [
        router.route_target_design(target_name="HSA", target_type="protein", route_hint="secreted protein"),
        router.route_target_design(target_name="GOI", target_type="gene", host_category="plant"),
        router.route_target_design(target_name="artemisinic acid"),
        router.route_target_design(target_name="healthy sugar in sugarcane", target_type="trait"),
        router.route_target_design(target_name="mystery target"),
    ]
    combined = "\n".join(_combined_text(draft).lower() for draft in drafts)
    forbidden = [
        "recommend" + "ation",
        "recommend" + "ed",
        "production" + "-ready",
        "experiment" + "-ready",
        "ready for " + "execution",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "guaranteed " + "expression",
        "guaranteed " + "activity",
        "protocol " + "generation",
        "therapeutic " + "success",
        "best promoter",
        "ranked part",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_service_has_no_streamlit_dependency() -> None:
    source = inspect.getsource(importlib.import_module("services.target_design_router"))

    assert "streamlit" not in source.lower()


def test_output_is_deterministic_for_repeated_calls() -> None:
    kwargs = {
        "target_name": "DHAA",
        "target_type": "pathway",
        "host_category": "plant",
        "specific_host": "Nicotiana benthamiana",
        "source_hint": "project source note",
    }

    assert router.route_target_design(**kwargs) == router.route_target_design(**kwargs)
