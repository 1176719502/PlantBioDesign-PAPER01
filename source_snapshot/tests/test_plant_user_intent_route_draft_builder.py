# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

import pytest

from services import plant_user_intent_route_draft_builder as builder
from services.plant_expression_route_template_registry import (
    get_plant_expression_route_template_by_id,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import (
    BLOCKED_OUTPUT_CATEGORIES,
    CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
)


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
}

FORBIDDEN_COPY = (
    "validated construct",
    "optimized pathway",
    "best",
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "wet-lab ready",
    "feasible",
)


def _draft(**intent: object) -> dict[str, object]:
    return builder.build_plant_expression_route_draft(intent)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _module_ids(draft: dict[str, object]) -> list[str]:
    return [module["module_id"] for module in draft["required_modules"]]  # type: ignore[index]


def _slot_statuses(draft: dict[str, object]) -> dict[str, str]:
    return {
        slot["slot_name"]: slot["status"]  # type: ignore[index]
        for slot in draft["required_slots"]  # type: ignore[index]
    }


def _walk_dicts(value: object) -> list[dict[str, object]]:
    dicts: list[dict[str, object]] = []
    if isinstance(value, dict):
        dicts.append(value)
        for nested in value.values():
            dicts.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for nested in value:
            dicts.extend(_walk_dicts(nested))
    return dicts


def test_generic_empty_intent_returns_safe_needs_input_draft() -> None:
    draft = builder.build_plant_expression_route_draft({})

    assert draft["draft_status"] == builder.DRAFT_STATUS_NEEDS_INPUT
    assert draft["manual_review_required"] is True
    assert draft["final_design_present"] is False
    assert draft["active_design_route"] is False
    assert draft["route_id"] == "unknown_plant_expression_context"
    assert draft["selected_template"] == {}
    assert draft["route_match"]["route_match_status"] == "unknown_or_ambiguous"  # type: ignore[index]
    assert draft["plant_context"]["scope_status"] == "missing_plant_route_context"  # type: ignore[index]
    assert draft["manual_review_items"][0]["review_type"] == "missing_route_context"  # type: ignore[index]
    assert "documentation-only" in draft["boundary_note"].casefold()  # type: ignore[attr-defined]
    assert "manual review" in draft["boundary_note"].casefold()  # type: ignore[attr-defined]
    assert draft["missing_inputs"] == ["plant_route_context"]


def test_invalid_non_mapping_input_raises_type_error() -> None:
    with pytest.raises(TypeError, match="intent must be a mapping or string"):
        builder.build_plant_expression_route_draft(["rice"])  # type: ignore[arg-type]


def test_plain_string_rice_seed_intent_prefers_r67_rice_template() -> None:
    draft = builder.build_plant_expression_route_draft(
        "I want to express human serum albumin in rice seed"
    )

    assert draft["manual_review_required"] is True
    assert draft["final_design_present"] is False
    assert draft["active_design_route"] is False
    assert draft["route_id"] == "rice_seed_protein_expression"
    assert draft["route_template_metadata"]["route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert draft["intent_summary"]["target_or_product_terms"] == "human serum albumin"  # type: ignore[index]
    assert draft["intent_summary"]["host_plant_terms"] == "rice"  # type: ignore[index]
    assert "rice seed" in draft["route_match"]["matched_host_context_terms"]  # type: ignore[index]
    assert draft["required_slots"] == draft["required_construct_slots"]
    assert draft["evidence_requirements"] == draft["selected_template"]["evidence_requirements"]  # type: ignore[index]


def test_generic_plant_expression_vector_string_uses_r67_default_template() -> None:
    draft = builder.build_plant_expression_route_draft(
        "generic plant expression vector review for a plant cassette"
    )

    assert draft["route_id"] == "plant_expression_vector"
    assert "plant expression vector" in draft["route_match"]["matched_trigger_terms"]  # type: ignore[index]
    assert draft["route_template_metadata"]["display_name"] == "Plant Expression Vector"  # type: ignore[index]


def test_rice_intent_selects_rice_route_if_available() -> None:
    draft = _draft(
        target_name="OsALB review target",
        plant_host="Oryza sativa rice",
        plant_context="rice seed expression context",
        expression_purpose="local documentation review",
        known_cds_source="SRC-CDS-001",
        known_vector_or_backbone="source-recorded backbone",
        known_component_ids={
            "promoter": "SRC-PROMOTER-001",
            "terminator": "SRC-TERM-001",
        },
        evidence_sources=["SRC-RICE-001"],
    )

    assert draft["route_id"] == "rice_seed_protein_expression"
    assert draft["selected_template"] == get_plant_expression_route_template_by_id(
        "rice_seed_protein_expression"
    )
    assert draft["route_match"]["candidate_route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert "rice" in draft["route_match"]["matched_host_context_terms"]  # type: ignore[index]
    assert draft["plant_context"]["selected_context"] == "rice_expression_vector"  # type: ignore[index]


@pytest.mark.parametrize(
    "host_name",
    ["N. benthamiana", "Nicotiana benthamiana", "benthamiana"],
)
def test_n_benthamiana_intent_selects_relevant_route_if_available(host_name: str) -> None:
    draft = _draft(
        target_name="leaf expression review target",
        plant_host=host_name,
        plant_context="leaf transient expression documentation context",
        expression_purpose="manual review",
    )

    assert draft["route_id"] == "plant_transient_expression_review"
    assert draft["selected_template"]["route_id"] == "plant_transient_expression_review"  # type: ignore[index]


def test_transient_reporter_string_preserves_matching_terms_for_manual_review() -> None:
    draft = builder.build_plant_expression_route_draft(
        "plant transient expression reporter review in Nicotiana leaves"
    )

    assert draft["route_id"] == "plant_transient_expression_review"
    assert "transient expression" in draft["route_match"]["matched_trigger_terms"]  # type: ignore[index]
    assert draft["intent_summary"]["expression_context_terms"] == "transient expression"  # type: ignore[index]
    assert draft["intent_summary"]["tissue_context_terms"] == "leaves"  # type: ignore[index]
    assert draft["manual_review_required"] is True


def test_secretion_localization_context_selects_localization_related_route_context() -> None:
    draft = _draft(
        target_name="secreted protein target",
        plant_host="rice",
        plant_context="plant expression context",
        localization_context="secreted apoplast localization with signal peptide source review",
        known_component_ids={"signal_peptide": "SRC-SIGNAL-001"},
        evidence_sources=["SRC-LOC-001"],
    )

    assert draft["route_id"] == "plant_secreted_protein_expression"
    assert draft["plant_context"]["selected_context"] == "plant_secretion_localization"  # type: ignore[index]
    assert "signal_peptide_localization" in _module_ids(draft)


def test_stable_localization_and_reporter_route_triggers_are_supported() -> None:
    stable = builder.build_plant_expression_route_draft(
        "stable plant expression review for a plant line"
    )
    localized = builder.build_plant_expression_route_draft(
        "plant localization-tagged expression review with chloroplast context"
    )
    reporter = builder.build_plant_expression_route_draft("plant reporter expression review with GFP")

    assert stable["route_id"] == "stable_plant_expression_review"
    assert localized["route_id"] == "plant_localization_tagged_expression"
    assert reporter["route_id"] == "plant_reporter_expression_review"
    assert "localization tag" in localized["route_match"]["matched_trigger_terms"]  # type: ignore[index]
    assert "reporter expression" in reporter["route_match"]["matched_trigger_terms"]  # type: ignore[index]


def test_unknown_plant_host_falls_back_to_generic_plant_expression_route() -> None:
    draft = _draft(
        target_name="unknown plant review target",
        plant_host="unlisted plant host",
        plant_context="plant expression vector documentation",
        expression_purpose="manual route draft review",
    )

    assert draft["route_id"] == "plant_expression_vector"
    assert draft["plant_context"]["scope_status"] == "plant_scope_review"  # type: ignore[index]


def test_vague_vector_intent_returns_unknown_route_context_without_template_claim() -> None:
    draft = builder.build_plant_expression_route_draft("make a vector")

    assert draft["draft_status"] == builder.DRAFT_STATUS_MANUAL_REVIEW_REQUIRED
    assert draft["route_id"] == "unknown_plant_expression_context"
    assert draft["selected_template"] == {}
    assert draft["manual_review_required"] is True
    assert draft["missing_inputs"] == ["plant_route_context"]
    assert draft["blocked_outputs"] == list(BLOCKED_OUTPUT_CATEGORIES)


def test_non_plant_terms_do_not_create_non_plant_routes() -> None:
    draft = builder.build_plant_expression_route_draft("express GFP in E. coli")

    assert draft["route_id"] == "unsupported_non_plant_expression_context"
    assert draft["route_type"] == "unsupported_non_plant_expression_context"
    assert draft["selected_template"] == {}
    assert draft["route_match"]["route_match_status"] == "unsupported_non_plant_scope"  # type: ignore[index]
    assert "bacterial" not in draft["route_id"]  # type: ignore[operator]
    assert "yeast" not in draft["route_id"]  # type: ignore[operator]
    assert "mammalian" not in draft["route_id"]  # type: ignore[operator]
    assert draft["plant_context"]["scope_status"] == "unsupported_non_plant_scope"  # type: ignore[index]
    assert any(
        item["review_type"] == "unsupported_scope_review"
        for item in draft["manual_review_items"]  # type: ignore[index]
    )


def test_required_module_ids_resolve_through_r380_registry() -> None:
    draft = _draft(plant_host="rice")
    template = draft["selected_template"]

    assert len(_module_ids(draft)) == len(template["required_module_ids"])  # type: ignore[index]
    for module in draft["required_modules"]:  # type: ignore[index]
        card = get_plant_review_module_card_by_id(module["module_id"])
        assert module == card
        assert module["route_type"] == CURRENT_ACTIVE_PLANT_ROUTE_TYPE


def test_required_module_card_summaries_are_attached_from_r66_registry() -> None:
    draft = _draft(plant_host="rice")
    summaries = draft["module_card_summaries"]

    assert [summary["module_id"] for summary in summaries] == _module_ids(draft)  # type: ignore[index]
    assert all(summary["display_name"] for summary in summaries)  # type: ignore[index]
    assert all("boundary_notes" in summary for summary in summaries)  # type: ignore[operator]


def test_selected_route_id_resolves_through_r381_registry() -> None:
    draft = _draft(plant_host="rice")

    assert get_plant_expression_route_template_by_id(draft["route_id"]) == draft["selected_template"]


def test_missing_fields_are_detected_deterministically() -> None:
    intent = {
        "target_name": "partial rice target",
        "plant_host": "rice",
        "known_component_ids": {"promoter": "SRC-PROMOTER-001"},
    }
    first = builder.build_plant_expression_route_draft(intent)
    second = builder.build_plant_expression_route_draft(dict(reversed(list(intent.items()))))

    assert first == second
    assert first["missing_fields"] == [
        slot["slot_name"]
        for slot in first["required_slots"]  # type: ignore[index]
        if slot["status"] == "missing"
    ]
    statuses = _slot_statuses(first)
    assert statuses["target_name"] == "provided"
    assert statuses["promoter_slot"] == "provided"
    assert statuses["terminator_slot"] == "missing"


def test_evidence_summary_preserves_provided_evidence_pointers() -> None:
    draft = _draft(
        plant_host="rice",
        evidence_sources={
            "SRC-B": "backbone source note",
            "SRC-A": "target source note",
        },
    )

    assert draft["evidence_summary"] == [
        {"source_id": "SRC-A", "value": "target source note"},
        {"source_id": "SRC-B", "value": "backbone source note"},
    ]


def test_blocked_outputs_and_boundary_note_are_preserved() -> None:
    draft = _draft(plant_host="rice")

    assert draft["blocked_outputs"] == list(BLOCKED_OUTPUT_CATEGORIES)
    assert "documentation-only" in draft["boundary_note"].casefold()  # type: ignore[attr-defined]
    assert "manual review" in draft["boundary_note"].casefold()  # type: ignore[attr-defined]


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(
        _draft(
            target_name="plain output target",
            plant_host="rice",
            known_component_ids={"promoter": "SRC-PROMOTER-001"},
            evidence_sources=["SRC-001"],
        )
    )


def test_no_unsafe_fields_are_present_anywhere_in_output() -> None:
    draft = _draft(plant_host="rice", localization_context="secretion")

    for item in _walk_dicts(draft):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)


def test_no_streamlit_db_import_export_agent_cloud_sequence_or_biorecommendation_runtime() -> None:
    source = Path("services/plant_user_intent_route_draft_builder.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_route",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source


def test_no_unsafe_copy_claims_are_present_in_runtime_output_or_source() -> None:
    draft_text = str(_draft(plant_host="rice")).casefold()
    source_text = Path("services/plant_user_intent_route_draft_builder.py").read_text(
        encoding="utf-8"
    ).casefold()

    for forbidden in FORBIDDEN_COPY:
        assert forbidden not in draft_text
        assert forbidden not in source_text


def test_route_draft_builder_does_not_import_ui_network_or_database_clients(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant route draft builder must stay local and offline for tests")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = _draft(plant_host="rice")

    assert result["route_id"] == "rice_seed_protein_expression"
    importlib.reload(builder)
