from __future__ import annotations

import importlib
import inspect
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import target_design_router as router
from services import target_design_router_preview as previewer


def _preview_text(value) -> str:
    return previewer.preview_text(value).lower()


def test_preview_has_stable_top_level_keys() -> None:
    preview = previewer.build_target_design_preview(
        router.route_target_design(
            target_name="GOI",
            target_type="gene",
            host_category="plant",
            gene_list=["GOI"],
        )
    )

    assert list(preview) == [
        "target_summary",
        "design_route_summary",
        "construct_template_summary",
        "gene_slots_table",
        "cassette_slots_table",
        "required_parts_table",
        "missing_fields_table",
        "source_requirements_table",
        "review_notes",
        "support_status",
        "boundary_note",
        "readiness_label",
    ]
    assert preview["target_summary"]["target_label"] == "GOI"
    assert preview["design_route_summary"]["route_label"] == "route preview"
    assert preview["readiness_label"] == "Needs source review"


def test_preview_can_consume_hsa_route_result() -> None:
    route_result = router.route_target_design(
        target_name="HSA",
        target_type="protein",
        host_category="plant",
        specific_host="Nicotiana benthamiana",
        expression_purpose="protein expression",
        route_hint="secreted protein",
        source_hint="local source note",
    )
    preview = previewer.build_target_design_preview(route_result)

    assert preview["target_summary"]["target_label"] == "HSA"
    assert preview["target_summary"]["aliases"] == ["human serum albumin", "albumin"]
    assert preview["design_route_summary"]["design_route"] == "secreted_protein_expression"
    assert preview["gene_slots_table"][0]["gene_label"] == "HSA"
    assert [row["slot_role"] for row in preview["cassette_slots_table"]] == [
        "promoter",
        "signal peptide",
        "CDS",
        "terminator",
    ]
    assert preview["readiness_label"] == "Ready for manual design review"


def test_preview_can_call_router_from_target_inputs() -> None:
    preview = previewer.build_target_design_preview(
        target_name="generic GOI",
        target_type="single gene",
        host_category="plant",
        gene_list=["GOI"],
        route_hint="single gene",
    )

    assert preview["target_summary"]["target_class"] == "single_gene"
    assert preview["design_route_summary"]["design_route"] == "single_goi_expression"
    assert preview["gene_slots_table"][0]["source_requirement"] == "GOI CDS source/provenance required"
    assert [row["slot_role"] for row in preview["cassette_slots_table"]] == [
        "promoter",
        "CDS",
        "terminator",
    ]


def test_preview_preserves_artemisinin_gene_and_cassette_slots() -> None:
    preview = previewer.build_target_design_preview(
        router.route_target_design(
            target_name="artemisinin precursor",
            target_type="pathway",
            host_category="plant",
            specific_host="Nicotiana benthamiana",
            route_hint="multi-gene pathway",
        )
    )

    expected_genes = ["ADS", "CYP71AV1", "CPR", "ADH1", "DBR2", "ALDH1"]
    assert [row["gene_label"] for row in preview["gene_slots_table"]] == expected_genes
    assert [row["slot_role"] for row in preview["cassette_slots_table"]] == [
        role
        for _gene in expected_genes
        for role in ["promoter", "CDS", "terminator"]
    ]
    assert {row["field"] for row in preview["missing_fields_table"]} >= {
        "promoter_choices",
        "CDS_sources",
        "terminators",
        "host",
        "vector_backbone",
        "source_or_reference_confirmation",
    }
    assert preview["boundary_note"] == (
        "This is a documentation-only pathway construct draft, not production, "
        "yield, or experimental validation."
    )
    assert preview["readiness_label"] == "Needs source review"


def test_preview_marks_sugarcane_healthy_sugar_as_needing_clarification() -> None:
    preview = previewer.build_target_design_preview(
        router.route_target_design(
            target_name="sugarcane healthy sugar",
            target_type="trait",
            host_category="plant",
            specific_host="sugarcane",
        )
    )

    assert preview["target_summary"]["target_class"] == "trait_or_phenotype"
    assert preview["design_route_summary"]["design_route"] == "needs_target_clarification"
    assert preview["gene_slots_table"] == []
    assert preview["cassette_slots_table"] == []
    assert preview["readiness_label"] == "Needs target clarification"
    notes = "\n".join(preview["review_notes"])
    assert "sweet protein expression" in notes
    assert "rare sugar enzyme expression" in notes
    assert "steviol glycoside pathway" in notes
    assert "sugar metabolism modification" in notes


def test_preview_handles_unknown_target_safely() -> None:
    preview = previewer.build_target_design_preview(router.route_target_design(target_name="mystery target"))

    assert preview["target_summary"]["target_class"] == "unresolved_target"
    assert preview["design_route_summary"]["design_route"] == "needs_target_clarification"
    assert preview["gene_slots_table"] == []
    assert preview["cassette_slots_table"] == []
    assert preview["readiness_label"] == "Needs target clarification"
    assert "documentation-only" in preview["boundary_note"].lower()


def test_preview_has_no_streamlit_dependency() -> None:
    source = inspect.getsource(importlib.import_module("services.target_design_router_preview"))

    assert "streamlit" not in source.lower()


def test_preview_output_is_deterministic() -> None:
    kwargs = {
        "target_name": "DHAA",
        "target_type": "pathway",
        "host_category": "plant",
        "specific_host": "Nicotiana benthamiana",
        "source_hint": "project source note",
    }

    assert previewer.build_target_design_preview(**kwargs) == previewer.build_target_design_preview(**kwargs)


def test_preview_text_avoids_forbidden_user_visible_claims() -> None:
    previews = [
        previewer.build_target_design_preview(target_name="HSA", target_type="protein", route_hint="secreted protein"),
        previewer.build_target_design_preview(target_name="GOI", target_type="gene", host_category="plant"),
        previewer.build_target_design_preview(target_name="artemisinic acid"),
        previewer.build_target_design_preview(target_name="healthy sugar in sugarcane", target_type="trait"),
        previewer.build_target_design_preview(target_name="mystery target"),
    ]
    combined = "\n".join(_preview_text(preview) for preview in previews)
    combined = combined.replace("not production, yield, or experimental validation", "")
    combined = combined.replace("not experimental validation", "")
    forbidden = [
        "recommend" + "ation",
        "recommend" + "ed",
        "optimization",
        "prediction",
        "production readiness",
        "wet-lab readiness",
        "experimental success",
        "validated design",
        "guaranteed expression",
        "purity",
        "activity",
        "therapeutic success",
        "ready for experiment",
        "ready for production",
        "validated",
        "optimized",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
