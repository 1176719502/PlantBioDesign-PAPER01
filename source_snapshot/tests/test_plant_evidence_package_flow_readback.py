from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_construct_slot_plan_readback_builder import build_plant_construct_slot_plan_readback
from services.plant_design_review_package_snapshot import build_plant_design_review_package_snapshot
from services.plant_evidence_package_flow_readback import (
    FLOW_KEYS,
    build_plant_evidence_package_flow_readback,
)
from services.plant_route_draft_presenter import present_plant_route_draft
from services.plant_route_gap_manual_review_queue import build_plant_route_gap_manual_review_queue
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


def _term(*parts: str) -> str:
    return "".join(parts)


def _route_draft() -> dict[str, Any]:
    return build_plant_expression_route_draft(
        {
            "target_name": "R414 evidence flow target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-414",
            "known_component_ids": {"promoter": "SRC-PROMOTER-414"},
            "known_vector_or_backbone": "SRC-BACKBONE-414",
            "evidence_sources": {"SRC-RICE-414": "rice host source pointer"},
        }
    )


def _flow_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    draft = _route_draft()
    presenter = present_plant_route_draft(draft)
    candidate = build_plant_component_candidate_match_readback(
        draft,
        [
            {
                "component_id": "COMP-PROMOTER-414",
                "component_name": "Rice promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
            }
        ],
    )
    gap_queue = build_plant_route_gap_manual_review_queue(draft, presenter, candidate)
    package = build_plant_design_review_package_snapshot(draft, presenter, candidate, gap_queue)
    slot_plan = build_plant_construct_slot_plan_readback(draft.get("selected_template"), draft.get("required_modules"))
    return slot_plan, gap_queue, package


def _assert_plain_dict_list(value: Any) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_dict_list(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_dict_list(nested)
    else:
        assert value is None or isinstance(value, (str, int, bool))


def _copy_blob(value: Any) -> str:
    values: list[str] = []

    def collect(nested: Any) -> None:
        if isinstance(nested, dict):
            for item in nested.values():
                collect(item)
        elif isinstance(nested, list):
            for item in nested:
                collect(item)
        else:
            values.append(str(nested))

    collect(value)
    return "\n".join(values).casefold()


def test_flow_readback_builds_evidence_gap_package_and_handoff_sections() -> None:
    slot_plan, gap_queue, package = _flow_inputs()

    flow = build_plant_evidence_package_flow_readback(slot_plan, gap_queue, package)

    assert list(flow) == list(FLOW_KEYS)
    assert flow["flow_status"] == "manual_review_required"
    assert flow["route_summary"]["route_template_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert flow["evidence_records"]
    assert flow["gap_review_items"]
    assert flow["package_sections"]
    assert flow["handoff_summary"]["evidence_record_count"] == len(flow["evidence_records"])  # type: ignore[index]
    assert flow["handoff_summary"]["gap_review_item_count"] == len(flow["gap_review_items"])  # type: ignore[index]
    assert flow["empty_state"]["is_empty"] is False  # type: ignore[index]


def test_evidence_records_preserve_slot_module_and_source_context() -> None:
    flow = build_plant_evidence_package_flow_readback(*_flow_inputs())

    promoter = next(
        row for row in flow["evidence_records"] if row["linked_slot_id"] == "promoter_slot"  # type: ignore[index]
    )
    assert promoter["linked_module_id"] == "plant_expression_cassette"
    assert promoter["source_label"] == "Plant Expression Cassette"
    assert promoter["source_type"] == "slot_plan_readback"
    assert promoter["package_section"] == "expression cassette slot plan"
    assert promoter["manual_review_status"] == "manual_review_required"


def test_gap_review_items_preserve_manual_review_questions() -> None:
    flow = build_plant_evidence_package_flow_readback(*_flow_inputs())

    gap = flow["gap_review_items"][0]  # type: ignore[index]
    assert gap["item_id"].startswith("plant-route-gap-")
    assert gap["gap_type"]
    assert gap["review_question"]
    assert gap["handoff_section"] == "manual review follow-up"
    assert gap["boundary_notes"]


def test_empty_input_returns_safe_empty_state() -> None:
    flow = build_plant_evidence_package_flow_readback()

    assert list(flow) == list(FLOW_KEYS)
    assert flow["flow_status"] == "empty_manual_review_required"
    assert flow["evidence_records"] == []
    assert flow["gap_review_items"] == []
    assert flow["package_sections"] == []
    assert flow["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert "documentation-only" in flow["boundary_notice"].casefold()  # type: ignore[index]


def test_flow_output_is_deterministic_and_plain_data() -> None:
    inputs = _flow_inputs()

    assert build_plant_evidence_package_flow_readback(*inputs) == build_plant_evidence_package_flow_readback(*inputs)
    _assert_plain_dict_list(build_plant_evidence_package_flow_readback(*inputs))


def test_no_positive_claim_copy_is_introduced() -> None:
    flow = build_plant_evidence_package_flow_readback(*_flow_inputs())
    blob = _copy_blob(flow)
    disallowed_phrases = [
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("valid", "ated ", "con", "struct"),
        _term("optimized ", "pathway"),
        _term("yield ", "pre", "diction"),
        _term("wet", "-lab ", "ready"),
        _term("recom", "mended"),
        _term("best"),
        _term("rank", "ing"),
        _term("scor", "ing"),
    ]

    for phrase in disallowed_phrases:
        assert phrase not in blob


def test_service_does_not_import_runtime_or_high_risk_surfaces() -> None:
    source = Path("services/plant_evidence_package_flow_readback.py").read_text(
        encoding="utf-8"
    ).casefold()
    disallowed_markers = [
        "streamlit",
        "sqlite",
        "project_import",
        "project_export",
        "package_export",
        "expression_wizard",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "generate_route",
        "generate_sequence",
        "recommend_component",
        "recommend_route",
        "select_promoter",
        "select_vector",
        "codon_optimization",
        "score_feasibility",
        "wet_lab_ready",
    ]

    for marker in disallowed_markers:
        assert marker not in source
