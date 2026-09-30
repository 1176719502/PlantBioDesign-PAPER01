# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

from services import plant_review_package_builder as builder
from services.plant_review_module_card_schema import CURRENT_ACTIVE_PLANT_ROUTE_TYPE


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "to build"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("guaranteed ", "expression"),
    _term("high", "-yield"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("expression", "-ready"),
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
    return builder.build_plant_review_package(
        route,
        evidence,
        component,
        queue,
        package_metadata={"review_batch": "R74"},
        user_context={"target": "rice albumin", "plant_host": "Oryza sativa"},
        **overrides,
    )


def test_complete_plant_payload_builds_review_ready_package_without_component_choice() -> None:
    result = _package()

    assert result["package_status"] == "review_ready"
    assert result["manual_review_required"] is True
    assert result["package_type"] == "plant_review_package"
    assert result["route_summary"]["route_id"] == "plant_expression_vector_rice_albumin"
    assert result["route_summary"]["route_template_id"] == "plant_expression_vector_template"
    assert result["route_summary"]["matched_trigger_terms"] == ["plant expression"]
    assert result["design_intent_summary"]["target_terms"] == ["rice albumin"]
    assert result["construct_slot_summary"]["total_slots"] == 1
    assert result["evidence_summary"]["evidence_ids"] == ["EV-PROMOTER"]
    assert result["component_candidate_summary"]["component_ids"] == ["COMP-PROMOTER-RICE"]
    assert result["gap_manual_review_summary"]["review_queue_total"] == 1
    rendered = str(result).casefold()
    assert "final_component" not in rendered
    assert "selected_component" not in rendered
    assert "winner" not in rendered


def test_missing_required_slot_increments_count_and_preserves_queue_traceability() -> None:
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
    result = _package(route_draft=route, gap_manual_review_queue_result=_queue(item))

    assert result["package_status"] == "manual_review_required"
    assert result["construct_slot_summary"]["missing_required_slot_count"] == 1
    assert result["gap_manual_review_summary"]["missing_required_slot_count"] == 1
    assert result["review_queue"][0]["slot_id"] == "promoter_slot"
    assert "missing_promoter_slot" in result["review_queue"][0]["manual_review_reasons"]


def test_evidence_exists_but_no_component_candidate_increments_component_gap() -> None:
    item = {
        "item_id": "r72-001-component-gap-promoter",
        "category": "component_gap",
        "severity": "review_required",
        "priority": 50,
        "route_id": "plant_expression_vector_rice_albumin",
        "slot_id": "promoter_slot",
        "evidence_ids": ["EV-PROMOTER"],
        "upstream_review_reasons": ["manual_review_required", "missing_component_candidate"],
        "note": "Slot has matched evidence but no component candidate.",
    }
    component = _component_result(slot_status="missing_component_candidate", candidate={})
    result = _package(component_candidate_match_result=component, gap_manual_review_queue_result=_queue(item))

    assert result["package_status"] == "manual_review_required"
    assert result["component_candidate_summary"]["component_gap_count"] == 1
    assert result["gap_manual_review_summary"]["component_gap_count"] == 1
    assert result["evidence_summary"]["evidence_ids"] == ["EV-PROMOTER"]
    assert result["review_queue"][0]["evidence_ids"] == ["EV-PROMOTER"]


def test_component_candidate_missing_provenance_increments_review_count() -> None:
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
    result = _package(
        component_candidate_match_result=_component_result(candidate=candidate),
        gap_manual_review_queue_result=_queue(item),
    )

    assert result["component_candidate_summary"]["provenance_gap_count"] == 1
    assert result["gap_manual_review_summary"]["provenance_gap_count"] == 1
    assert result["component_candidate_summary"]["slots"][0]["candidate_components"][0]["missing_provenance"] is True


def test_duplicate_alias_candidate_increments_ambiguity_without_auto_merge() -> None:
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
        "note": "Component candidate has duplicate or alias signals and must not be auto-merged.",
    }
    result = _package(
        component_candidate_match_result=_component_result(candidate=candidate),
        gap_manual_review_queue_result=_queue(item),
    )

    assert result["component_candidate_summary"]["duplicate_or_alias_count"] == 1
    assert result["gap_manual_review_summary"]["ambiguity_or_duplicate_count"] == 1
    assert "auto-merged" in str(result).casefold()
    assert "winner" not in str(result).casefold()


def test_unsupported_non_plant_draft_blocks_package() -> None:
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
    result = _package(route_draft=route, gap_manual_review_queue_result=_queue(item))

    assert result["package_status"] == "blocked"
    assert result["manual_review_required"] is True
    assert result["gap_manual_review_summary"]["unsupported_scope_count"] == 1
    assert result["gap_manual_review_summary"]["blocker_count"] == 1


def test_empty_and_malformed_inputs_fail_safe_with_warnings() -> None:
    empty = builder.build_plant_review_package({}, {}, [], None)
    malformed = _package(route_draft={"route_type": CURRENT_ACTIVE_PLANT_ROUTE_TYPE})

    assert empty["package_status"] == "empty_or_invalid_input"
    assert empty["manual_review_required"] is True
    assert empty["traceability"]["source_payloads_present"]["route_draft"] is False
    assert any("missing upstream result warning" in warning for warning in empty["package_warnings"])
    assert malformed["package_status"] == "manual_review_required"
    assert any("route_id is missing" in warning for warning in malformed["package_warnings"])


def test_package_output_is_plain_dict_list_string_bool_number_data() -> None:
    _assert_plain_data(_package())


def test_package_builder_stays_offline_ui_db_import_export_and_sequence_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant review package builder must stay local and offline")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    assert _package()["package_status"] == "review_ready"
    importlib.reload(builder)


def test_package_builder_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(_package()).casefold()
    source_text = Path("services/plant_review_package_builder.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "manual review" in result_text
