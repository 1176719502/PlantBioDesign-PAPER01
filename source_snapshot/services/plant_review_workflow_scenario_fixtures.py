from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_review_workflow_chain_runner import run_plant_review_workflow_chain


SCENARIO_FIXTURE_SCHEMA_VERSION = "plant_review_workflow_scenario_fixtures.v2.7.r77"
SCENARIO_FIXTURE_BATCH = "v2.7-r77"

RICE_SEED_PROTEIN_EXPRESSION_REVIEW = "rice_seed_protein_expression_review"
PLANT_TRANSIENT_EXPRESSION_REVIEW = "plant_transient_expression_review"
GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW = "generic_plant_expression_vector_review"
UNSUPPORTED_NON_PLANT_SCOPE = "unsupported_non_plant_scope"
EMPTY_OR_VAGUE_INPUT = "empty_or_vague_input"

SCENARIO_IDS = (
    RICE_SEED_PROTEIN_EXPRESSION_REVIEW,
    PLANT_TRANSIENT_EXPRESSION_REVIEW,
    GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW,
    UNSUPPORTED_NON_PLANT_SCOPE,
    EMPTY_OR_VAGUE_INPUT,
)


def _rice_seed_protein_expression_review_input() -> dict[str, Any]:
    return {
        "scenario_id": RICE_SEED_PROTEIN_EXPRESSION_REVIEW,
        "fixture_schema_version": SCENARIO_FIXTURE_SCHEMA_VERSION,
        "user_intent": {
            "target_name": "rice seed albumin-like protein",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression review context",
            "tissue_context": "seed",
            "expression_purpose": "local documentation review",
            "known_cds_source": "rice albumin-like CDS source note",
            "known_vector_or_backbone": "plant binary vector source note",
            "known_component_ids": {
                "promoter": "rice seed promoter source note",
            },
            "evidence_sources": ["local rice seed evidence note"],
        },
        "evidence_records": [
            {
                "id": "R77-RICE-EV-CDS",
                "paper_title": "Rice albumin-like protein identity source",
                "summary": "Local source note for a rice seed albumin-like protein review context.",
                "publication_year": "2024",
                "journal": "Local citation index",
                "tags": "rice, seed, albumin, plant",
                "design_context": {"target_product": "rice seed albumin-like protein"},
                "provenance_note": "Curated local source metadata.",
            },
            {
                "id": "R77-RICE-EV-PROMOTER",
                "paper_title": "Rice seed promoter source metadata",
                "summary": "Local note for a rice seed promoter source context.",
                "publication_year": "2023",
                "journal": "Local citation index",
                "tags": "rice, seed, promoter, plant",
                "design_context": {"promoter": "rice seed promoter"},
                "provenance_note": "Curated local source metadata.",
            },
        ],
        "component_records": [
            {
                "component_id": "R77-RICE-COMP-CDS",
                "component_name": "Rice albumin-like CDS source component record",
                "component_type": "cds_source",
                "design_slot_tags": ["cds_label", "coding_sequence_slot"],
                "plant_context": "Oryza sativa rice seed",
                "aliases": ["rice albumin-like CDS source note"],
                "matched_evidence_ids": ["R77-RICE-EV-CDS"],
                "source_label": "local CDS source record",
                "source_reference": "R77-RICE-EV-CDS",
                "provenance_status": "source provenance recorded",
                "provenance_note": "Curated local component source metadata.",
            },
            {
                "component_id": "R77-RICE-COMP-PROMOTER-GAP",
                "component_name": "Rice seed promoter component record needing source follow-up",
                "component_type": "promoter",
                "design_slot_tags": ["promoter_slot"],
                "plant_context": "rice seed expression review context",
                "aliases": ["rice seed promoter source note"],
                "matched_evidence_ids": ["R77-RICE-EV-PROMOTER"],
            },
        ],
        "context": {
            "query": "rice seed protein expression review",
            "plant_context": "rice seed expression review context",
        },
        "options": {"package_metadata": {"review_batch": SCENARIO_FIXTURE_BATCH}},
    }


def _plant_transient_expression_review_input() -> dict[str, Any]:
    return {
        "scenario_id": PLANT_TRANSIENT_EXPRESSION_REVIEW,
        "fixture_schema_version": SCENARIO_FIXTURE_SCHEMA_VERSION,
        "user_intent": {
            "target_name": "transient reporter expression review",
            "plant_host": "Nicotiana benthamiana",
            "plant_context": "transient plant expression context",
            "expression_purpose": "local documentation review",
            "known_vector_or_backbone": "plant transient expression vector note",
            "evidence_sources": ["local transient plant evidence note"],
        },
        "evidence_records": [
            {
                "id": "R77-TR-EV-CONTEXT",
                "paper_title": "Nicotiana transient expression source context",
                "summary": "Local note for N. benthamiana transient expression review context.",
                "publication_year": "2024",
                "journal": "Local citation index",
                "tags": "Nicotiana benthamiana, transient, plant",
                "design_context": {"plant_context": "transient expression"},
                "provenance_note": "Curated local source metadata.",
            }
        ],
        "component_records": [
            {
                "component_id": "R77-TR-COMP-VECTOR",
                "component_name": "Plant transient expression vector component record",
                "component_type": "vector_backbone",
                "design_slot_tags": ["vector_backbone_slot"],
                "plant_context": "Nicotiana benthamiana transient expression",
                "matched_evidence_ids": ["R77-TR-EV-CONTEXT"],
                "source_label": "local vector source record",
                "source_reference": "R77-TR-EV-CONTEXT",
                "provenance_status": "source provenance recorded",
                "provenance_note": "Curated local component source metadata.",
            }
        ],
        "context": {
            "query": "Nicotiana benthamiana transient plant expression review",
            "plant_context": "transient plant expression context",
        },
        "options": {"package_metadata": {"review_batch": SCENARIO_FIXTURE_BATCH}},
    }


def _generic_plant_expression_vector_review_input() -> dict[str, Any]:
    return {
        "scenario_id": GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW,
        "fixture_schema_version": SCENARIO_FIXTURE_SCHEMA_VERSION,
        "user_intent": {
            "target_name": "plant expression vector review",
            "plant_host": "plant",
            "plant_context": "general plant expression vector context",
            "expression_purpose": "local documentation review",
        },
        "evidence_records": [],
        "component_records": [],
        "context": {
            "query": "general plant expression vector review",
            "plant_context": "general plant expression vector context",
        },
        "options": {"package_metadata": {"review_batch": SCENARIO_FIXTURE_BATCH}},
    }


def _unsupported_non_plant_scope_input() -> dict[str, Any]:
    return {
        "scenario_id": UNSUPPORTED_NON_PLANT_SCOPE,
        "fixture_schema_version": SCENARIO_FIXTURE_SCHEMA_VERSION,
        "user_intent": "express GFP in E. coli for non-plant expression review",
        "evidence_records": [],
        "component_records": [],
        "context": {"query": "non-plant expression review"},
        "options": {"package_metadata": {"review_batch": SCENARIO_FIXTURE_BATCH}},
    }


def _empty_or_vague_input() -> dict[str, Any]:
    return {
        "scenario_id": EMPTY_OR_VAGUE_INPUT,
        "fixture_schema_version": SCENARIO_FIXTURE_SCHEMA_VERSION,
        "user_intent": {},
        "evidence_records": [],
        "component_records": [],
        "context": {"query": ""},
        "options": {"package_metadata": {"review_batch": SCENARIO_FIXTURE_BATCH}},
    }


_SCENARIO_BUILDERS = {
    RICE_SEED_PROTEIN_EXPRESSION_REVIEW: _rice_seed_protein_expression_review_input,
    PLANT_TRANSIENT_EXPRESSION_REVIEW: _plant_transient_expression_review_input,
    GENERIC_PLANT_EXPRESSION_VECTOR_REVIEW: _generic_plant_expression_vector_review_input,
    UNSUPPORTED_NON_PLANT_SCOPE: _unsupported_non_plant_scope_input,
    EMPTY_OR_VAGUE_INPUT: _empty_or_vague_input,
}


def list_plant_review_workflow_scenario_ids() -> list[str]:
    return list(SCENARIO_IDS)


def build_plant_review_workflow_scenario_input(scenario_id: str) -> dict[str, Any]:
    builder = _SCENARIO_BUILDERS.get(str(scenario_id or ""))
    if builder is None:
        raise ValueError(f"unknown plant review workflow scenario fixture: {scenario_id}")
    return deepcopy(builder())


def build_all_plant_review_workflow_scenario_inputs() -> list[dict[str, Any]]:
    return [build_plant_review_workflow_scenario_input(scenario_id) for scenario_id in SCENARIO_IDS]


def run_plant_review_workflow_scenario_fixture(scenario_id: str) -> dict[str, Any]:
    fixture_input = build_plant_review_workflow_scenario_input(scenario_id)
    result = run_plant_review_workflow_chain(
        fixture_input["user_intent"],
        fixture_input["evidence_records"],
        fixture_input["component_records"],
        fixture_input.get("context"),
        fixture_input.get("options"),
    )
    result["scenario_id"] = fixture_input["scenario_id"]
    result["scenario_fixture_schema_version"] = SCENARIO_FIXTURE_SCHEMA_VERSION
    return result


def run_all_plant_review_workflow_scenario_fixtures() -> list[dict[str, Any]]:
    return [run_plant_review_workflow_scenario_fixture(scenario_id) for scenario_id in SCENARIO_IDS]
