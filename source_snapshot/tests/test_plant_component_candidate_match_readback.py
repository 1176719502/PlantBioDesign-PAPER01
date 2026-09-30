from __future__ import annotations

from pathlib import Path

from services.plant_component_candidate_match_readback import (
    READBACK_SECTION_KEYS,
    build_plant_component_candidate_match_readback,
)
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


FORBIDDEN_FIELD_NAMES = {
    "recommendation",
    "optimization",
    "feasibility_score",
    "yield_prediction",
    "protocol",
    "wet_lab_ready",
    "validated",
    "build_ready",
    "best",
}


def _rice_route_draft() -> dict[str, object]:
    return build_plant_expression_route_draft(
        {
            "target_name": "OsALB candidate match target",
            "target_type": "source-backed plant expression target",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression documentation context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "SRC-CDS-384",
            "known_component_ids": {
                "promoter": "SRC-PROMOTER-384",
                "terminator": "SRC-TERMINATOR-384",
            },
            "known_vector_or_backbone": "SRC-BACKBONE-384",
            "evidence_sources": {
                "SRC-RICE-384": "rice host context source pointer",
                "SRC-CDS-384": "target CDS source pointer",
            },
            "notes": "Manual documentation review note.",
        }
    )


def _component_records() -> list[dict[str, object]]:
    return [
        {
            "component_id": "COMP-TERM-384",
            "component_name": "Rice terminator candidate record",
            "component_type": "terminator_slot",
            "slot_type": "terminator_slot",
            "plant_context": "rice seed expression documentation context",
            "evidence_status": "source pointer recorded",
            "source_id": "SRC-TERM-384",
            "source_label": "terminator source record",
            "citation": "source citation pointer",
            "notes": "Preserve source note.",
            "review_status": "manual review pending",
        },
        {
            "component_id": "COMP-PROMOTER-B",
            "component_name": "Alternate rice promoter candidate record",
            "component_type": "promoter_slot",
            "slot_type": "promoter_slot",
            "plant_context": "rice seed expression documentation context",
            "evidence_status": "source pointer recorded",
            "source_id": "SRC-PROMOTER-B",
            "source_label": "alternate promoter source record",
            "review_status": "manual review pending",
        },
        {
            "component_id": "COMP-PROMOTER-A",
            "component_name": "Rice promoter candidate record",
            "component_type": "promoter_slot",
            "slot_type": "promoter_slot",
            "plant_context": "rice seed expression documentation context",
            "evidence_status": "source pointer recorded",
            "source_id": "SRC-PROMOTER-A",
            "source_label": "promoter source record",
            "review_status": "manual review pending",
        },
    ]


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


def test_normal_rice_route_draft_with_matching_component_records_produces_candidate_rows() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())

    assert list(readback) == list(READBACK_SECTION_KEYS)
    assert readback["empty_state"]["is_empty"] is False  # type: ignore[index]
    assert readback["route_summary"]["route_id"] == "rice_seed_protein_expression"  # type: ignore[index]
    assert readback["candidate_match_summary"]["total_candidate_rows"] == 3  # type: ignore[index]
    assert {row["slot_type"] for row in readback["slot_candidate_rows"]} >= {  # type: ignore[index]
        "promoter_slot",
        "terminator_slot",
    }


def test_unmatched_slots_produce_manual_review_rows() -> None:
    readback = build_plant_component_candidate_match_readback(
        _rice_route_draft(),
        [
            {
                "component_id": "COMP-PROMOTER-ONLY",
                "component_name": "Promoter only",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "plant_context": "rice seed expression documentation context",
            }
        ],
    )

    unmatched = readback["unmatched_slot_rows"]
    assert unmatched
    assert all(row["candidate_status"] == "missing_candidate" for row in unmatched)  # type: ignore[index]
    assert all(row["manual_review_required"] is True for row in unmatched)  # type: ignore[index]
    assert any(item["review_type"] == "missing_candidate" for item in readback["manual_review_items"])  # type: ignore[index]


def test_multiple_candidates_for_one_slot_are_preserved_deterministically() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())
    promoter_rows = [
        row for row in readback["slot_candidate_rows"] if row["slot_type"] == "promoter_slot"  # type: ignore[index]
    ]

    assert [row["component_id"] for row in promoter_rows] == ["COMP-PROMOTER-A", "COMP-PROMOTER-B"]
    assert build_plant_component_candidate_match_readback(
        _rice_route_draft(),
        list(reversed(_component_records())),
    )["slot_candidate_rows"] == readback["slot_candidate_rows"]


def test_plant_context_match_is_candidate_context_match_not_recommendation() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())

    assert {row["candidate_context_status"] for row in readback["slot_candidate_rows"]} == {  # type: ignore[index]
        "candidate_context_match"
    }
    assert "recommendation" not in str(readback["slot_candidate_rows"]).casefold()
    assert "recommendation" not in str(readback["candidate_match_summary"]).casefold()


def test_non_plant_component_records_are_excluded_and_marked_for_manual_review() -> None:
    readback = build_plant_component_candidate_match_readback(
        _rice_route_draft(),
        [
            {
                "component_id": "COMP-ECOLI-PROMOTER",
                "component_name": "Bacterial promoter record",
                "component_type": "promoter_slot",
                "slot_type": "promoter_slot",
                "host_context": "E. coli bacterial host",
            }
        ],
    )

    assert readback["slot_candidate_rows"] == []
    assert readback["candidate_match_summary"]["out_of_scope_component_records"] == 1  # type: ignore[index]
    assert any(
        item["review_type"] == "out_of_scope_component_records"
        for item in readback["manual_review_items"]  # type: ignore[index]
    )


def test_empty_route_draft_returns_safe_empty_state() -> None:
    readback = build_plant_component_candidate_match_readback({}, _component_records())

    assert readback["empty_state"]["is_empty"] is True  # type: ignore[index]
    assert readback["route_summary"] == {}
    assert readback["slot_candidate_rows"] == []
    assert "documentation-only" in readback["boundary_notice"]["notice"].casefold()  # type: ignore[index]


def test_none_component_records_returns_safe_unmatched_readback() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), None)

    assert readback["candidate_match_summary"]["total_candidate_rows"] == 0  # type: ignore[index]
    assert readback["unmatched_slot_rows"]
    assert any(
        item["review_type"] == "component_records_needed"
        for item in readback["manual_review_items"]  # type: ignore[index]
    )


def test_evidence_fields_are_preserved_in_candidate_and_evidence_rows() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())
    row = next(row for row in readback["slot_candidate_rows"] if row["component_id"] == "COMP-TERM-384")  # type: ignore[index]

    assert row["evidence_status"] == "source pointer recorded"
    assert row["source_id"] == "SRC-TERM-384"
    assert row["source_label"] == "terminator source record"
    assert row["citation"] == "source citation pointer"
    assert row["review_status"] == "manual review pending"
    assert any(
        evidence["component_id"] == "COMP-TERM-384"
        and evidence["evidence_context_status"] == "candidate_evidence_context_recorded"
        for evidence in readback["evidence_coverage_rows"]  # type: ignore[index]
    )


def test_boundary_notice_and_blocked_outputs_notice_are_present() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())

    assert "documentation-only" in readback["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert "manual review" in readback["boundary_notice"]["notice"].casefold()  # type: ignore[index]
    assert "blocked output" in readback["blocked_outputs_notice"]["title"].casefold()  # type: ignore[index]


def test_no_final_component_selection_is_produced() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())
    text = str(readback).casefold()

    assert "final_component" not in text
    assert "selected_component" not in text
    assert "winner" not in text


def test_no_unsafe_field_names_are_present_anywhere_in_output() -> None:
    readback = build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records())

    for item in _walk_dicts(readback):
        assert FORBIDDEN_FIELD_NAMES.isdisjoint(item)


def test_output_is_plain_dict_list_only() -> None:
    _assert_plain_data(build_plant_component_candidate_match_readback(_rice_route_draft(), _component_records()))


def test_no_ui_db_import_export_package_expression_wizard_or_runtime_behavior_is_introduced() -> None:
    source = Path("services/plant_component_candidate_match_readback.py").read_text(encoding="utf-8").casefold()

    disallowed_runtime_markers = [
        "streamlit",
        "sqlite",
        "project_export",
        "project_import",
        "package_export",
        "expression_wizard",
        "openai",
        "requests",
        "httpx",
        "agent_runtime",
        "cloud_runtime",
        "generate_sequence",
        "sequence_output",
        "recommend_component",
        "optimize_sequence",
        "score_feasibility",
        "wet_lab_ready",
    ]
    for marker in disallowed_runtime_markers:
        assert marker not in source
