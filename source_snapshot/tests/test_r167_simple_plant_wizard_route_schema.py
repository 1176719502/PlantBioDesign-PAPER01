from __future__ import annotations

import os
import sys
from typing import Any


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    build_simple_plant_wizard_route_summary,
    get_simple_plant_wizard_entry_routes,
    get_simple_plant_wizard_handoff_stage,
    get_simple_plant_wizard_route,
    get_simple_plant_wizard_routes,
)


ENTRY_ROUTE_IDS = [
    "plant_protein_expression_review",
    "plant_metabolic_pathway_review",
    "plant_multigene_construct_review",
    "plant_regulatory_module_review",
]

BEGINNER_ROUTE_FIELDS = {
    "route_id",
    "route_kind",
    "label_en",
    "label_zh",
    "button_label_zh",
    "short_description_zh",
    "examples_zh",
    "primary_user_goal_zh",
    "required_slots",
    "clarification_prompts_zh",
    "safe_boundary_notes_zh",
    "handoff_stage_id",
}

PLAIN_TYPES = (dict, list, str, bool, int)


def _walk_plain_values(value: Any) -> None:
    assert isinstance(value, PLAIN_TYPES)
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _walk_plain_values(item)
    elif isinstance(value, list):
        for item in value:
            _walk_plain_values(item)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return str(value)


def test_all_entry_routes_are_present_and_stable() -> None:
    routes = get_simple_plant_wizard_entry_routes()

    assert [route["route_id"] for route in routes] == ENTRY_ROUTE_IDS
    assert [route["route_kind"] for route in routes] == ["entry_route"] * 4


def test_handoff_package_stage_is_shared_and_not_an_entry_route() -> None:
    entry_routes = get_simple_plant_wizard_entry_routes()
    handoff_stage = get_simple_plant_wizard_handoff_stage()

    assert handoff_stage["route_id"] == HANDOFF_STAGE_ID
    assert handoff_stage["route_kind"] == "shared_handoff_stage"
    assert HANDOFF_STAGE_ID not in [route["route_id"] for route in entry_routes]
    assert handoff_stage["applies_to_route_ids"] == ENTRY_ROUTE_IDS


def test_every_entry_route_points_to_shared_handoff_stage() -> None:
    for route in get_simple_plant_wizard_entry_routes():
        assert route["handoff_stage_id"] == HANDOFF_STAGE_ID


def test_entry_routes_include_beginner_facing_labels_examples_and_prompts() -> None:
    for route in get_simple_plant_wizard_entry_routes():
        assert BEGINNER_ROUTE_FIELDS.issubset(route)
        assert route["label_en"]
        assert route["label_zh"]
        assert route["button_label_zh"]
        assert route["short_description_zh"]
        assert route["primary_user_goal_zh"]
        assert len(route["examples_zh"]) >= 2
        assert all(example.strip() for example in route["examples_zh"])
        assert route["required_slots"]
        assert route["clarification_prompts_zh"]
        assert route["safe_boundary_notes_zh"]


def test_route_required_slots_match_r167_contract() -> None:
    expected_slots = {
        "plant_protein_expression_review": [
            "target_protein",
            "gene_or_cds",
            "host_plant",
            "expression_context",
            "promoter",
            "signal_or_transit_peptide",
            "terminator",
            "marker_or_reporter",
            "vector_or_backbone",
            "evidence_records",
            "manual_review_status",
        ],
        "plant_metabolic_pathway_review": [
            "target_product",
            "pathway_overview",
            "pathway_step",
            "precursor_or_intermediate",
            "enzyme_or_gene_candidate",
            "subcellular_localization",
            "host_plant",
            "pathway_evidence",
            "enzyme_evidence",
            "missing_pathway_steps",
            "manual_review_status",
        ],
        "plant_multigene_construct_review": [
            "construct_goal",
            "gene_list",
            "cassette_list",
            "cassette_promoters",
            "cassette_genes",
            "cassette_terminators",
            "cassette_order",
            "module_relationships",
            "vector_or_backbone",
            "marker_or_reporter",
            "evidence_records",
            "manual_review_status",
        ],
        "plant_regulatory_module_review": [
            "regulatory_goal",
            "input_signal",
            "sensor_or_promoter",
            "transcription_factor_or_regulator",
            "cis_element",
            "output_gene",
            "expression_pattern",
            "reporter_or_readout",
            "host_context",
            "regulatory_evidence",
            "uncertainty_or_risk",
            "manual_review_status",
        ],
    }

    for route_id, slots in expected_slots.items():
        assert get_simple_plant_wizard_route(route_id)["required_slots"] == slots


def test_summary_payload_includes_route_and_handoff_counts() -> None:
    summary = build_simple_plant_wizard_route_summary()

    assert summary["entry_route_count"] == 4
    assert summary["shared_handoff_stage_count"] == 1
    assert summary["total_route_count"] == 5
    assert summary["entry_route_ids"] == ENTRY_ROUTE_IDS
    assert summary["shared_handoff_stage_id"] == HANDOFF_STAGE_ID
    assert summary["documentation_only"] is True
    assert summary["manual_review_required"] is True


def test_schema_is_deterministic_and_returns_mutation_safe_copies() -> None:
    first = get_simple_plant_wizard_routes()
    second = get_simple_plant_wizard_routes()
    assert first == second

    first[0]["required_slots"].append("mutated")
    assert get_simple_plant_wizard_routes() == second


def test_returned_data_is_plain_dict_list_str_bool_int_only() -> None:
    _walk_plain_values(get_simple_plant_wizard_routes())
    _walk_plain_values(build_simple_plant_wizard_route_summary())


def test_safety_boundary_notes_avoid_forbidden_claims() -> None:
    forbidden_fragments = [
        "valid" + "ated",
        "optim" + "ized",
        "experiment" + "-ready",
        "proto" + "col",
        "yield" + " prediction",
        "best" + " component",
    ]
    route_blob = _text_blob(get_simple_plant_wizard_routes()).casefold()
    summary_blob = _text_blob(build_simple_plant_wizard_route_summary()).casefold()

    for fragment in forbidden_fragments:
        assert fragment not in route_blob
        assert fragment not in summary_blob
