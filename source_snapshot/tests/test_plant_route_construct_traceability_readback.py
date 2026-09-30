# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_route_construct_traceability_readback as readback


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("recommended ", "component"),
    _term("best ", "component"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("wet", "-lab", "-ready"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "pre", "diction"),
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


def _route_context() -> dict[str, Any]:
    return {
        "route_id": "rice-seed-protein-route",
        "route_type": "plant_expression_vector",
        "plant_goal": "Rice seed protein expression documentation review",
        "plant_context": "rice seed context",
    }


def _intent() -> dict[str, Any]:
    return {
        "target_name": "rice seed albumin-like protein",
        "plant_host": "Oryza sativa rice",
        "tissue_context": "seed",
    }


def _evidence_slot_result(*, missing_source: bool = False) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "record_id": "EV-PROMOTER",
        "title": "Rice seed promoter source note",
        "source_type": "local literature placeholder",
        "review_status": "manual_review_required",
        "manual_review_reasons": ["manual_review_required"],
        "source_completeness": {
            "has_title": True,
            "has_source": not missing_source,
            "missing_metadata": ["source"] if missing_source else [],
        },
    }
    if not missing_source:
        candidate["source"] = {
            "source_label": "local promoter citation",
            "source_identifier": "PMID:100001",
            "source_type": "literature_placeholder",
        }
    return {
        "matcher_status": "plant_slot_evidence_candidates_for_manual_review",
        "manual_review_required": True,
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_label": "Promoter and leader",
                "slot_status": "candidate_evidence_manual_review",
                "candidate_evidence": [candidate],
                "manual_review_reasons": ["manual_review_required"],
            }
        ],
    }


def _component_candidate_result(
    *,
    missing_source: bool = False,
    missing_evidence_link: bool = False,
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "component_id": "COMP-PROMOTER-RICE",
        "component_name": "Rice seed promoter component record",
        "component_type": "promoter",
        "matched_evidence_ids": [] if missing_evidence_link else ["EV-PROMOTER"],
        "provenance_status": "source_provenance_missing" if missing_source else "source_provenance_recorded",
        "source_completeness": {
            "has_source": not missing_source,
            "has_provenance": not missing_source,
            "has_evidence_link": not missing_evidence_link,
            "missing_fields": (
                ["source", "provenance"]
                if missing_source
                else ["evidence_link"]
                if missing_evidence_link
                else []
            ),
        },
        "manual_review_reasons": ["manual_review_required"],
        "manual_review_note": "Component source context needs reviewer signoff.",
    }
    if missing_source:
        candidate["manual_review_reasons"].append("missing_provenance_or_source")
    if missing_evidence_link:
        candidate["manual_review_reasons"].append("component_slot_linkage_gap")
    if not missing_source:
        candidate["traceability"] = {
            "source_label": "local promoter component source",
            "source_reference": "EV-PROMOTER",
        }
    return {
        "matcher_status": "plant_component_candidates_for_manual_review",
        "manual_review_required": True,
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_label": "Promoter and leader",
                "slot_status": "component_candidates_for_manual_review",
                "matched_evidence_ids": [] if missing_evidence_link else ["EV-PROMOTER"],
                "candidate_components": [candidate],
                "manual_review_reasons": ["manual_review_required"],
            }
        ],
    }


def _manual_review_queue() -> dict[str, Any]:
    return {
        "queue_status": "plant_gap_manual_review_queue",
        "manual_review_required": True,
        "review_items": [
            {
                "item_id": "review-promoter-provenance",
                "category": "provenance_gap",
                "severity": "review_required",
                "slot_id": "promoter_slot",
                "evidence_ids": ["EV-PROMOTER"],
                "component_ids": ["COMP-PROMOTER-RICE"],
                "upstream_review_reasons": ["manual_review_required", "missing_provenance_or_source"],
                "note": "Confirm the component source/provenance trail.",
            }
        ],
        "blocked_output_categories": ["protocol", "final_biological_solution"],
    }


def _construct_readback() -> dict[str, Any]:
    return {
        "readback_status": "construct_draft_readback_created",
        "manual_review_required": True,
        "slot_rows": [
            {
                "slot_name": "promoter",
                "display_label": "Promoter",
                "status": "needs_confirmation",
                "safe_status_text": "needs confirmation; manual review required",
                "evidence_ids": ["EV-PROMOTER"],
                "source_ids": ["EV-PROMOTER"],
                "missing_reason": "",
                "manual_review_required": True,
            },
            {
                "slot_name": "vector_backbone",
                "display_label": "Vector backbone",
                "status": "needs_source",
                "safe_status_text": "missing source; manual review required",
                "evidence_ids": [],
                "source_ids": [],
                "missing_reason": "vector source record not linked",
                "manual_review_required": True,
            },
        ],
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "plant_project_intent": _intent(),
        "route_context": _route_context(),
        "evidence_slot_match_result": _evidence_slot_result(),
        "component_candidate_match_result": _component_candidate_result(),
        "gap_manual_review_queue_result": _manual_review_queue(),
        "construct_draft_readback": _construct_readback(),
    }
    kwargs.update(overrides)
    return readback.build_plant_route_construct_traceability_readback(**kwargs)


def test_populated_route_to_construct_trace_rows_are_readable_and_plain() -> None:
    payload = _payload()
    rows = payload["traceability_section"]["rows"]
    promoter_row = rows[0]

    assert payload["traceability_schema_version"] == readback.TRACEABILITY_SCHEMA_VERSION
    assert payload["traceability_status"] == readback.TRACEABILITY_STATUS_READY
    assert payload["read_only"] is True
    assert payload["plant_scope_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["reuse_source"] == "plant_evidence_review_worksheet_presenter"
    assert promoter_row["route_or_context_id"] == "rice-seed-protein-route"
    assert "rice seed albumin-like protein" in promoter_row["intent_summary"]
    assert payload["summary"]["trace_row_count"] == 2
    assert payload["summary"]["construct_slot_count"] == 2
    assert payload["summary"]["manual_review_required"] is True
    _assert_plain_data(payload)


def test_evidence_to_component_slot_linkage_is_preserved() -> None:
    row = _payload()["traceability_section"]["rows"][0]

    assert row["linked_evidence_id"] == "EV-PROMOTER"
    assert row["linked_component"] == "COMP-PROMOTER-RICE | Rice seed promoter component record"
    assert row["linked_component_slot"] == "promoter_slot | Promoter and leader"
    assert row["source_or_provenance_status"] == "source/provenance recorded: local promoter component source, EV-PROMOTER"


def test_component_slot_to_construct_slot_linkage_is_preserved() -> None:
    payload = _payload()
    promoter_row = payload["traceability_section"]["rows"][0]
    vector_row = payload["traceability_section"]["rows"][1]

    assert promoter_row["linked_construct_slot"] == "promoter"
    assert vector_row["linked_construct_slot"] == "vector_backbone"
    assert vector_row["linked_component"] == "component not recorded"
    assert vector_row["gap_or_followup_reason"] == "vector source record not linked"


def test_missing_evidence_or_provenance_produces_safe_gap_status() -> None:
    payload = _payload(
        evidence_slot_match_result=_evidence_slot_result(missing_source=True),
        component_candidate_match_result=_component_candidate_result(
            missing_source=True,
            missing_evidence_link=True,
        ),
    )
    row = payload["traceability_section"]["rows"][0]

    assert row["linked_evidence_id"] == ""
    assert row["source_or_provenance_status"] == "source/provenance gap"
    assert "missing_provenance_or_source" in row["gap_or_followup_reason"]
    assert "component_slot_linkage_gap" in row["gap_or_followup_reason"]
    assert row["review_status"] == "manual_review_required"
    assert payload["summary"]["gap_or_followup_count"] >= 1


def test_manual_review_and_followup_reasons_propagate() -> None:
    row = _payload(
        handoff_review_items=[
            {
                "item_id": "handoff-promoter-check",
                "category": "handoff_review",
                "severity": "review_required",
                "slot_id": "promoter_slot",
                "evidence_ids": ["EV-PROMOTER"],
                "component_ids": ["COMP-PROMOTER-RICE"],
                "reason": "handoff reviewer should compare source trail",
                "note": "Use local review record before downstream interpretation.",
            }
        ]
    )["traceability_section"]["rows"][0]

    assert "handoff reviewer should compare source trail" in row["gap_or_followup_reason"]
    assert "Use local review record before downstream interpretation." in row["manual_review_note"]
    assert "Component source context needs reviewer signoff." in row["manual_review_note"]


def test_empty_input_returns_safe_payload() -> None:
    payload = readback.build_plant_route_construct_traceability_readback()

    assert payload["traceability_status"] == readback.TRACEABILITY_STATUS_EMPTY
    assert payload["read_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["summary"]["empty_input"] is True
    assert payload["summary"]["trace_row_count"] == 0
    assert payload["traceability_section"]["rows"] == []
    assert payload["construct_slot_section"]["rows"] == []
    assert payload["handoff_review_section"]["rows"] == []
    assert payload["warnings"] == [
        "traceability input warning: no readable plant route, evidence, component, or construct payload was provided"
    ]


def test_deterministic_ids_and_stable_keys() -> None:
    first = _payload()
    second = _payload()
    rows = first["traceability_section"]["rows"]

    assert first == second
    assert first["stable_keys"]["traceability_row_keys"] == list(readback.TRACEABILITY_ROW_KEYS)
    assert first["stable_keys"]["construct_slot_row_keys"] == list(readback.CONSTRUCT_SLOT_ROW_KEYS)
    assert first["stable_keys"]["handoff_review_row_keys"] == list(readback.HANDOFF_REVIEW_ROW_KEYS)
    assert all(set(row) == set(readback.TRACEABILITY_ROW_KEYS) for row in rows)
    assert rows[0]["trace_id"] == "r128-trace-001-rice_seed_protein_route-promoter-ev_promoter"
    assert rows[1]["trace_id"] == "r128-trace-002-rice_seed_protein_route-vector_backbone-component_not_recorded"


def test_source_avoids_copy_that_would_imply_choice_or_downstream_claims() -> None:
    payload_text = str(_payload()).casefold()
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_route_construct_traceability_readback.py"
    ).read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in payload_text
        assert phrase not in service_text

    assert "documentation_readback" in payload_text
    assert "manual review" in payload_text
