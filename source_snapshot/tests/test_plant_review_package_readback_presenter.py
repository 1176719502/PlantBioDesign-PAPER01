# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_review_package_builder as package_builder
from services.plant_review_module_card_schema import CURRENT_ACTIVE_PLANT_ROUTE_TYPE
from services.plant_review_package_readback_presenter import (
    SECTION_KEYS,
    build_plant_review_package_readback_presenter,
)


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "to build"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("guaranteed ", "expression"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("build", "-ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _route(slot_status: str = "documented") -> dict[str, Any]:
    return {
        "route_id": "plant_expression_vector_rice_albumin",
        "route_label": "Rice albumin plant expression vector review",
        "route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
        "draft_status": "route_draft_for_manual_review",
        "selected_template": {
            "route_id": "plant_expression_vector_template",
            "route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE,
            "display_name": "Plant Expression Vector",
            "required_slots": ["promoter_slot"],
            "blocked_outputs": ["protocol", "yield_prediction"],
            "trigger_terms": ["plant expression", "vector record"],
            "supported_host_contexts": ["Oryza sativa seed"],
        },
        "route_match": {
            "matched_trigger_terms": ["plant expression"],
            "matched_context_terms": ["rice seed"],
        },
        "target_summary": {
            "target_name": "rice albumin",
            "known_cds_source": "OsAlbumin source note",
        },
        "plant_context": {
            "provided_host": "Oryza sativa",
            "provided_context": "seed expression context",
            "scope_status": "plant_scope_review",
        },
        "required_slots": [
            {
                "slot_id": "promoter_slot",
                "slot_label": "Promoter and leader",
                "slot_status": slot_status,
                "required": True,
                "slot_value": "rice seed promoter source note",
            }
        ],
        "module_card_summaries": [
            {
                "module_id": "plant_expression_vector_intake",
                "module_label": "Plant Expression Vector Intake",
                "required_slots": ["promoter_slot"],
                "blocked_outputs": ["protocol", "optimized_sequence"],
            }
        ],
        "manual_review_reasons": ["manual_review_required"],
    }


def _evidence_result(slot_status: str = "candidate_evidence_manual_review") -> dict[str, Any]:
    return {
        "schema_version": "r69-test",
        "matcher_status": "plant_slot_evidence_candidates_for_manual_review",
        "plant_scope_supported": True,
        "manual_review_required": True,
        "route_context": {"route_id": "plant_expression_vector_rice_albumin"},
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_label": "Promoter and leader",
                "slot_status": slot_status,
                "candidate_evidence": [{"record_id": "EV-PROMOTER"}],
                "source_completeness": {
                    "has_title": True,
                    "has_source": True,
                    "missing_metadata": [],
                },
            }
        ],
    }


def _component_result(
    *,
    slot_status: str = "component_candidates_for_manual_review",
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if candidate is None:
        candidate = {
            "component_id": "COMP-PROMOTER-RICE",
            "component_type": "promoter",
            "matched_evidence_ids": ["EV-PROMOTER"],
            "provenance_status": "source_provenance_recorded",
            "source_completeness": {
                "has_source": True,
                "has_provenance": True,
                "has_evidence_link": True,
                "missing_fields": [],
            },
            "duplicate_or_alias_flag": False,
            "manual_review_reasons": ["manual_review_required"],
        }
    return {
        "matcher_version": "r70-test",
        "matcher_status": "plant_component_candidates_for_manual_review",
        "plant_scope_supported": True,
        "manual_review_required": True,
        "route_context": {"route_id": "plant_expression_vector_rice_albumin"},
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_label": "Promoter and leader",
                "slot_status": slot_status,
                "matched_evidence_ids": ["EV-PROMOTER"],
                "candidate_components": [candidate] if candidate else [],
            }
        ],
    }


def _queue(*items: dict[str, Any]) -> dict[str, Any]:
    if not items:
        items = (
            {
                "item_id": "r72-001-blocked-output-boundary-route-context",
                "category": "blocked_output_boundary",
                "severity": "informational",
                "priority": 80,
                "route_id": "plant_expression_vector_rice_albumin",
                "source_references": ["protocol"],
                "upstream_review_reasons": ["manual_review_required"],
                "note": "Blocked output categories remain documentation-only boundary reminders.",
            },
        )
    return {
        "queue_version": "r72-test",
        "queue_status": "plant_gap_manual_review_queue",
        "plant_scope_supported": True,
        "manual_review_required": True,
        "review_items": list(items),
        "blocked_output_categories": ["protocol", "yield_prediction"],
        "summary": {"total_items": len(items)},
    }


def _package(**overrides: Any) -> dict[str, Any]:
    route = overrides.pop("route_draft", _route())
    evidence = overrides.pop("evidence_slot_match_result", _evidence_result())
    component = overrides.pop("component_candidate_match_result", _component_result())
    queue = overrides.pop("gap_manual_review_queue_result", _queue())
    return package_builder.build_plant_review_package(
        route,
        evidence,
        component,
        queue,
        package_metadata={"review_batch": "R75"},
        user_context={"target": "rice albumin", "plant_host": "Oryza sativa"},
        **overrides,
    )


def test_full_r74_package_builds_stable_readback_sections() -> None:
    presenter = build_plant_review_package_readback_presenter(_package())

    assert list(presenter) == list(SECTION_KEYS)
    assert presenter["empty_state"]["empty_state"] is False
    assert presenter["package_header"]["package_type"] == "plant_review_package"
    assert presenter["status_summary_card"]["status_label"] == "review_ready"
    assert "documentation-only" in presenter["status_summary_card"]["safe_boundary_note"].casefold()
    assert presenter["route_summary_section"]["route_template_id"] == "plant_expression_vector_template"
    assert presenter["module_card_section"]["rows"][0]["module_id"] == "plant_expression_vector_intake"
    assert presenter["construct_slot_section"]["rows"][0]["evidence_count"] == 1
    assert presenter["evidence_section"]["rows"][0]["evidence_ids"] == ["EV-PROMOTER"]
    assert presenter["component_candidate_section"]["rows"][0]["component_ids"] == ["COMP-PROMOTER-RICE"]
    assert presenter["review_queue_section"]["rows"][0]["category"] == "blocked_output_boundary"
    assert presenter == build_plant_review_package_readback_presenter(_package())


def test_missing_required_slot_marks_slot_and_preserves_gap_queue() -> None:
    item = {
        "item_id": "r72-001-required-slot-gap-promoter",
        "category": "required_slot_gap",
        "severity": "review_required",
        "priority": 30,
        "route_id": "plant_expression_vector_rice_albumin",
        "module_id": "plant_expression_vector_intake",
        "slot_id": "promoter_slot",
        "slot_label": "Promoter and leader",
        "upstream_review_reasons": ["manual_review_required", "missing_promoter_slot"],
        "note": "Required slot is not filled in the route draft.",
    }
    route = _route(slot_status="missing")
    route["missing_fields"] = ["promoter_slot"]
    presenter = build_plant_review_package_readback_presenter(
        _package(route_draft=route, gap_manual_review_queue_result=_queue(item))
    )

    slot = presenter["construct_slot_section"]["rows"][0]
    assert slot["missing_required_slot"] is True
    assert slot["review_state"] == "manual_review_needed"
    assert presenter["gap_manual_review_section"]["counts"]["required_slot_gap"] == 1
    assert presenter["review_queue_section"]["rows"][0]["slot_id"] == "promoter_slot"


def test_evidence_gap_is_marked_without_validation_claim() -> None:
    item = {
        "item_id": "r72-001-evidence-gap-promoter",
        "category": "evidence_gap",
        "severity": "review_required",
        "priority": 40,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "promoter_slot",
        "upstream_review_reasons": ["manual_review_required", "missing_evidence"],
        "note": "Construct slot lacks evidence records for documentation review.",
    }
    presenter = build_plant_review_package_readback_presenter(
        _package(
            evidence_slot_match_result=_evidence_result(slot_status="missing_evidence"),
            gap_manual_review_queue_result=_queue(item),
        )
    )

    row = presenter["evidence_section"]["rows"][0]
    assert row["evidence_gap"] is True
    assert presenter["gap_manual_review_section"]["counts"]["evidence_gap"] == 1
    assert "validat" not in str(presenter).casefold()


def test_component_provenance_gap_preserves_component_and_manual_review_flag() -> None:
    candidate = {
        "component_id": "COMP-PROMOTER-MISSING-SOURCE",
        "component_type": "promoter",
        "matched_evidence_ids": ["EV-PROMOTER"],
        "provenance_status": "source_provenance_missing",
        "source_completeness": {
            "has_source": False,
            "has_provenance": False,
            "has_evidence_link": True,
            "missing_fields": ["source", "provenance"],
        },
        "manual_review_reasons": ["manual_review_required", "missing_provenance_or_source"],
    }
    item = {
        "item_id": "r72-001-provenance-gap-promoter",
        "category": "provenance_gap",
        "severity": "review_required",
        "priority": 60,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "promoter_slot",
        "evidence_ids": ["EV-PROMOTER"],
        "component_ids": ["COMP-PROMOTER-MISSING-SOURCE"],
        "upstream_review_reasons": ["manual_review_required", "missing_provenance_or_source"],
        "note": "Component candidate source or provenance metadata is incomplete.",
    }
    presenter = build_plant_review_package_readback_presenter(
        _package(
            component_candidate_match_result=_component_result(candidate=candidate),
            gap_manual_review_queue_result=_queue(item),
        )
    )

    row = presenter["component_candidate_section"]["rows"][0]
    assert row["component_ids"] == ["COMP-PROMOTER-MISSING-SOURCE"]
    assert row["provenance_status"] == "source_provenance_missing"
    assert row["manual_review_required"] is True
    assert presenter["gap_manual_review_section"]["counts"]["provenance_gap"] == 1


def test_duplicate_alias_candidate_preserves_flag_without_component_choice() -> None:
    candidate = {
        "component_id": "COMP-PROMOTER-ALIAS",
        "component_type": "promoter",
        "matched_evidence_ids": ["EV-PROMOTER"],
        "provenance_status": "source_provenance_recorded",
        "source_completeness": {
            "has_source": True,
            "has_provenance": True,
            "has_evidence_link": True,
            "missing_fields": [],
        },
        "duplicate_or_alias_flag": True,
        "manual_review_reasons": ["manual_review_required", "duplicate_or_alias_review"],
    }
    item = {
        "item_id": "r72-001-ambiguity-promoter",
        "category": "ambiguity_or_duplicate_review",
        "severity": "review_required",
        "priority": 70,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "promoter_slot",
        "component_ids": ["COMP-PROMOTER-ALIAS"],
        "upstream_review_reasons": ["manual_review_required", "duplicate_or_alias_review"],
        "note": "Component candidate has duplicate or alias signals.",
    }
    presenter = build_plant_review_package_readback_presenter(
        _package(
            component_candidate_match_result=_component_result(candidate=candidate),
            gap_manual_review_queue_result=_queue(item),
        )
    )

    row = presenter["component_candidate_section"]["rows"][0]
    text = str(presenter).casefold()
    assert row["duplicate_or_alias_flag"] is True
    assert presenter["gap_manual_review_section"]["counts"]["ambiguity_or_duplicate_review"] == 1
    assert "final_component" not in text
    assert "selected_component" not in text
    assert "winner" not in text


def test_unsupported_non_plant_package_shows_blocked_scope_review() -> None:
    route = _route()
    route["route_id"] = "unsupported_non_plant_expression_context"
    route["route_type"] = "bacterial_expression"
    route["plant_context"]["scope_status"] = "unsupported_non_plant_scope"
    item = {
        "item_id": "r72-001-unsupported-scope",
        "category": "unsupported_scope",
        "severity": "blocker",
        "priority": 10,
        "route_id": "unsupported_non_plant_expression_context",
        "upstream_review_reasons": ["supported_plant_route_context"],
        "note": "Route draft is outside the supported Plant Expression Vector review scope.",
    }
    presenter = build_plant_review_package_readback_presenter(
        _package(route_draft=route, gap_manual_review_queue_result=_queue(item))
    )

    assert presenter["status_summary_card"]["status_label"] == "blocked"
    assert presenter["gap_manual_review_section"]["counts"]["unsupported_scope"] == 1
    assert presenter["review_queue_section"]["rows"][0]["category"] == "unsupported_scope"
    assert presenter["route_summary_section"]["unsupported_or_mixed_scope_notes"]


def test_blocked_output_categories_are_only_boundary_section_categories() -> None:
    presenter = build_plant_review_package_readback_presenter(_package())

    boundary = presenter["blocked_output_boundary_section"]
    assert "protocol" in boundary["blocked_output_categories"]
    assert "yield_prediction" in boundary["blocked_output_categories"]
    assert "generated outputs or product claims" in boundary["boundary_note"]
    assert "protocol" not in str(presenter["status_summary_card"]).casefold()


def test_empty_and_malformed_input_return_safe_empty_state() -> None:
    for payload in (None, {}, {"package_type": "plant_review_package"}):
        presenter = build_plant_review_package_readback_presenter(payload)

        assert presenter["empty_state"]["empty_state"] is True
        assert presenter["empty_state"]["package_status"] == "empty_or_invalid_input"
        assert presenter["package_header"]["manual_review_required"] is True
        assert presenter["status_summary_card"]["safe_boundary_note"]
        assert presenter["warning_section"]["warnings"]

    empty_package = package_builder.build_plant_review_package({}, {}, [], None)
    presenter = build_plant_review_package_readback_presenter(empty_package)
    assert presenter["empty_state"]["empty_state"] is True
    assert presenter["empty_state"]["manual_review_required"] is True
    assert any("missing package payload" in warning for warning in presenter["warning_section"]["warnings"])


def test_review_queue_rows_are_sorted_deterministically() -> None:
    late = {
        "item_id": "late",
        "category": "component_gap",
        "severity": "review_required",
        "priority": 50,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "terminator_slot",
        "component_ids": ["COMP-Z"],
        "note": "Later row.",
    }
    early = {
        "item_id": "early",
        "category": "evidence_gap",
        "severity": "review_required",
        "priority": 20,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "promoter_slot",
        "evidence_ids": ["EV-A"],
        "note": "Earlier row.",
    }

    first = build_plant_review_package_readback_presenter(_package(gap_manual_review_queue_result=_queue(late, early)))
    second = build_plant_review_package_readback_presenter(_package(gap_manual_review_queue_result=_queue(early, late)))

    assert [row["item_id"] for row in first["review_queue_section"]["rows"]] == ["early", "late"]
    assert first["review_queue_section"]["rows"] == second["review_queue_section"]["rows"]


def test_traceability_preserves_upstream_versions_and_presenter_version() -> None:
    presenter = build_plant_review_package_readback_presenter(_package())
    traceability = presenter["traceability_section"]

    assert traceability["route_ids"] == ["plant_expression_vector_rice_albumin"]
    assert traceability["slot_ids"] == ["promoter_slot"]
    assert traceability["evidence_ids"] == ["EV-PROMOTER"]
    assert traceability["component_ids"] == ["COMP-PROMOTER-RICE"]
    assert traceability["upstream_result_versions"]["evidence_slot_match_result"] == "r69-test"
    assert traceability["upstream_result_versions"]["component_candidate_match_result"] == "r70-test"
    assert traceability["upstream_result_versions"]["gap_manual_review_queue_result"] == "r72-test"
    assert traceability["package_builder_version"] == "v2.7-r74"
    assert traceability["presenter_version"] == "v2.7-r75"


def test_presenter_output_is_plain_dict_list_string_bool_number_data() -> None:
    _assert_plain_data(build_plant_review_package_readback_presenter(_package()))


def test_presenter_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(build_plant_review_package_readback_presenter(_package())).casefold()
    source_text = Path("services/plant_review_package_readback_presenter.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "human review" in result_text
