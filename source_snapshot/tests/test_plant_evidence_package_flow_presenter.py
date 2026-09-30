from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_component_candidate_match_readback import build_plant_component_candidate_match_readback
from services.plant_construct_slot_plan_readback_builder import build_plant_construct_slot_plan_readback
from services.plant_design_review_package_snapshot import build_plant_design_review_package_snapshot
from services.plant_evidence_package_flow_presenter import (
    BOUNDARY_NOTICE,
    PRESENTER_KEYS,
    format_evidence_package_flow_markdown,
    present_evidence_package_flow_readback,
)
from services.plant_evidence_package_flow_readback import build_plant_evidence_package_flow_readback
from services.plant_route_draft_presenter import present_plant_route_draft
from services.plant_route_gap_manual_review_queue import build_plant_route_gap_manual_review_queue
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


def _term(*parts: str) -> str:
    return "".join(parts)


def _flow_readback() -> dict[str, Any]:
    draft = build_plant_expression_route_draft(
        {
            "target_name": "R415 evidence package presenter target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-415",
            "known_component_ids": {"promoter": "SRC-PROMOTER-415"},
            "known_vector_or_backbone": "SRC-BACKBONE-415",
            "evidence_sources": {"SRC-RICE-415": "rice host source pointer"},
        }
    )
    route_presenter = present_plant_route_draft(draft)
    candidate = build_plant_component_candidate_match_readback(
        draft,
        [
            {
                "component_id": "COMP-PROMOTER-415",
                "component_name": "Rice promoter source record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
            }
        ],
    )
    gap_queue = build_plant_route_gap_manual_review_queue(draft, route_presenter, candidate)
    package = build_plant_design_review_package_snapshot(draft, route_presenter, candidate, gap_queue)
    slot_plan = build_plant_construct_slot_plan_readback(draft.get("selected_template"), draft.get("required_modules"))
    return build_plant_evidence_package_flow_readback(slot_plan, gap_queue, package)


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


def test_presenter_formats_flow_readback_sections() -> None:
    presented = present_evidence_package_flow_readback(_flow_readback())

    assert list(presented) == list(PRESENTER_KEYS)
    assert presented["page_title"] == "Plant Evidence Package Flow Readback"
    assert presented["subtitle"] == "Documentation-only evidence, gap, package, and handoff summary for manual review."
    assert presented["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert presented["summary_card"]["evidence_record_count"] == len(presented["evidence_rows"])  # type: ignore[index]
    assert presented["summary_card"]["gap_review_item_count"] == len(presented["gap_rows"])  # type: ignore[index]
    assert presented["summary_card"]["package_section_count"] == len(presented["package_section_rows"])  # type: ignore[index]
    assert presented["route_card"]["route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert presented["handoff_card"]["handoff_status"] == "manual_review_required"  # type: ignore[index]
    assert "# Plant Evidence Package Flow Readback Snapshot" in presented["markdown_snapshot"]


def test_presenter_rows_preserve_evidence_gap_and_package_identity() -> None:
    presented = present_evidence_package_flow_readback(_flow_readback())

    evidence = presented["evidence_rows"][0]  # type: ignore[index]
    gap = presented["gap_rows"][0]  # type: ignore[index]
    section = presented["package_section_rows"][0]  # type: ignore[index]

    assert evidence["evidence_id"].startswith("plant-evidence-")
    assert evidence["linked_slot_id"]
    assert evidence["manual_review_status"] == "manual_review_required"
    assert gap["item_id"].startswith("plant-route-gap-")
    assert gap["handoff_section"] == "manual review follow-up"
    assert section["section_id"] == "route_summary"
    assert section["display_order"] == 1


def test_empty_input_returns_safe_empty_state() -> None:
    presented = present_evidence_package_flow_readback({})

    assert list(presented) == list(PRESENTER_KEYS)
    assert presented["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert presented["evidence_rows"] == []
    assert presented["gap_rows"] == []
    assert presented["package_section_rows"] == []
    assert presented["markdown_snapshot"] == ""


def test_markdown_snapshot_includes_sections_and_boundary() -> None:
    presented = present_evidence_package_flow_readback(_flow_readback())
    markdown = format_evidence_package_flow_markdown(presented)

    assert markdown.startswith("# Plant Evidence Package Flow Readback Snapshot")
    assert "## Summary" in markdown
    assert "## Evidence records" in markdown
    assert "## Gap review items" in markdown
    assert "## Package sections" in markdown
    assert "## Handoff summary" in markdown
    assert BOUNDARY_NOTICE in markdown


def test_presenter_output_is_deterministic_and_plain_data() -> None:
    flow = _flow_readback()

    assert present_evidence_package_flow_readback(flow) == present_evidence_package_flow_readback(flow)
    _assert_plain_dict_list(present_evidence_package_flow_readback(flow))


def test_no_positive_claim_copy_is_introduced() -> None:
    blob = _copy_blob(present_evidence_package_flow_readback(_flow_readback()))
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


def test_presenter_does_not_import_runtime_or_high_risk_surfaces() -> None:
    source = Path("services/plant_evidence_package_flow_presenter.py").read_text(
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
