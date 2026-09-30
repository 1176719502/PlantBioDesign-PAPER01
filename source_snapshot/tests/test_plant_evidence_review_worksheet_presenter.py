# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_evidence_review_worksheet_presenter as presenter


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
    _term("recommended ", "component"),
    _term("best ", "component"),
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
        "route_id": "plant_expression_vector_rice_albumin",
        "route_type": "plant_expression_vector",
        "draft_status": "route_draft_for_manual_review",
        "selected_template": {"route_id": "plant_expression_vector_template"},
        "plant_context": {"scope_status": "plant_scope_review"},
    }


def _evidence_slot_result(*, missing_source: bool = False, weak: bool = False) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "record_id": "EV-PROMOTER",
        "title": "Rice seed promoter source note",
        "source_type": "local literature placeholder",
        "review_status": "unreviewed" if weak else "manual_review_required",
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
    if weak:
        candidate["evidence_status"] = "weak"
        candidate["manual_review_reasons"].append("weak_evidence_placeholder")
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


def _component_candidate_result(*, missing_source: bool = False, linkage_gap: bool = False) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "component_id": "COMP-PROMOTER-RICE",
        "component_name": "Rice seed promoter component record",
        "component_type": "promoter",
        "matched_evidence_ids": [] if linkage_gap else ["EV-PROMOTER"],
        "provenance_status": "source_provenance_missing" if missing_source else "source_provenance_recorded",
        "source_completeness": {
            "has_source": not missing_source,
            "has_provenance": not missing_source,
            "has_evidence_link": not linkage_gap,
            "missing_fields": ["source", "provenance"] if missing_source else ["evidence_link"] if linkage_gap else [],
        },
        "manual_review_reasons": ["manual_review_required"],
    }
    if missing_source:
        candidate["manual_review_reasons"].append("missing_provenance_or_source")
    if linkage_gap:
        candidate["manual_review_reasons"].append("component_slot_linkage_gap")
    if not missing_source and not linkage_gap:
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
                "matched_evidence_ids": [] if linkage_gap else ["EV-PROMOTER"],
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
                "item_id": "r72-001-provenance-gap-promoter",
                "category": "provenance_gap",
                "severity": "review_required",
                "slot_id": "promoter_slot",
                "evidence_ids": ["EV-PROMOTER"],
                "component_ids": ["COMP-PROMOTER-RICE"],
                "upstream_review_reasons": ["manual_review_required", "missing_provenance_or_source"],
                "note": "Component candidate source or provenance metadata is incomplete.",
            }
        ],
        "blocked_output_categories": ["protocol", "yield_prediction", "final_biological_solution"],
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    kwargs = {
        "route_context": _route_context(),
        "evidence_slot_match_result": _evidence_slot_result(),
        "component_candidate_match_result": _component_candidate_result(),
        "gap_manual_review_queue_result": _manual_review_queue(),
    }
    kwargs.update(overrides)
    return presenter.build_plant_evidence_review_worksheet_payload(**kwargs)


def test_supported_populated_evidence_rows_are_readable_and_plain() -> None:
    payload = _payload()
    row = payload["evidence_review_section"]["rows"][0]
    summary = payload["summary"]

    assert payload["worksheet_schema_version"] == presenter.WORKSHEET_SCHEMA_VERSION
    assert payload["worksheet_status"] == presenter.SUPPORTED_WORKSHEET_STATUS
    assert payload["read_only"] is True
    assert payload["plant_scope_only"] is True
    assert payload["manual_review_required"] is True
    assert row["evidence_item_id"] == "EV-PROMOTER"
    assert row["evidence_label"] == "Rice seed promoter source note"
    assert row["source_or_provenance_placeholder"] == "local promoter citation, PMID:100001, literature_placeholder"
    assert row["documentation_only_boundary"] == presenter.WORKSHEET_BOUNDARY_STATEMENT
    assert summary["total_evidence_rows"] == 1
    assert summary["linked_component_slot_count"] == 1
    assert summary["manual_review_required_count"] == 3
    assert summary["blocked_boundary_category_count"] == 3
    assert summary["overall_review_state"] == presenter.OVERALL_STATE_REQUIRES_MANUAL_REVIEW
    assert summary["followup_queue_count"] > 0
    _assert_plain_data(payload)


def test_missing_source_or_provenance_placeholder_is_visible() -> None:
    payload = _payload(
        evidence_slot_match_result=_evidence_slot_result(missing_source=True),
        component_candidate_match_result=_component_candidate_result(missing_source=True),
    )
    evidence_row = payload["evidence_review_section"]["rows"][0]
    component_row = payload["component_slot_linkage_section"]["rows"][0]

    assert evidence_row["source_or_provenance_placeholder"] == "source/provenance placeholder missing"
    assert "missing_source" in evidence_row["gap_reason"]
    assert component_row["source_or_provenance_placeholder"] == "source/provenance placeholder missing"
    assert "missing_provenance_or_source" in component_row["gap_reason"]
    assert payload["summary"]["provenance_gap_count"] >= 2
    assert payload["summary"]["missing_source_or_provenance_count"] == 2
    followups = payload["followup_queue_section"]["rows"]
    assert any(row["followup_type"] == "missing_provenance" for row in followups)
    assert all(row["suggested_review_action"] for row in followups)


def test_weak_or_unreviewed_evidence_status_is_preserved() -> None:
    payload = _payload(evidence_slot_match_result=_evidence_slot_result(weak=True))
    row = payload["evidence_review_section"]["rows"][0]

    assert row["evidence_status"] == "weak"
    assert row["review_status"] == "unreviewed"
    assert "weak_evidence_placeholder" in row["gap_reason"]
    assert payload["summary"]["weak_or_unreviewed_evidence_count"] == 1
    assert payload["summary"]["overall_review_state"] == presenter.OVERALL_STATE_REQUIRES_MANUAL_REVIEW
    followups = payload["followup_queue_section"]["rows"]
    assert any(
        row["followup_type"] == "weak_or_unreviewed_evidence"
        and row["linked_evidence_id"] == "EV-PROMOTER"
        and row["suggested_review_action"] == "confirm evidence level and review status"
        for row in followups
    )


def test_followup_type_options_are_deterministic() -> None:
    payload = _payload(
        evidence_slot_match_result=_evidence_slot_result(missing_source=True, weak=True),
        component_candidate_match_result=_component_candidate_result(missing_source=True, linkage_gap=True),
    )

    assert presenter.followup_queue_type_options(payload["followup_queue_section"]) == [
        "boundary_only_category",
        "component_slot_linkage_gap",
        "manual_review_required",
        "missing_provenance",
        "weak_or_unreviewed_evidence",
    ]


def test_followup_filter_missing_provenance_returns_only_missing_provenance_rows() -> None:
    payload = _payload(
        evidence_slot_match_result=_evidence_slot_result(missing_source=True, weak=True),
        component_candidate_match_result=_component_candidate_result(missing_source=True, linkage_gap=True),
    )
    rows = presenter.filter_followup_queue_rows(
        payload["followup_queue_section"],
        followup_type="missing_provenance",
    )

    assert rows
    assert {row["followup_type"] for row in rows} == {"missing_provenance"}
    assert all("provenance" in row["reason"] or "source" in row["suggested_review_action"] for row in rows)


def test_followup_filter_weak_or_unreviewed_returns_only_weak_or_unreviewed_rows() -> None:
    payload = _payload(evidence_slot_match_result=_evidence_slot_result(missing_source=True, weak=True))
    rows = presenter.filter_followup_queue_rows(
        payload["followup_queue_section"],
        followup_type="weak_or_unreviewed_evidence",
    )

    assert rows
    assert {row["followup_type"] for row in rows} == {"weak_or_unreviewed_evidence"}
    assert all(row["suggested_review_action"] == "confirm evidence level and review status" for row in rows)


def test_manual_review_required_filter_preserves_manual_review_wording() -> None:
    payload = _payload()
    rows = presenter.filter_followup_queue_rows(
        payload["followup_queue_section"],
        followup_type="manual_review_required",
    )

    assert rows
    assert {row["followup_type"] for row in rows} == {"manual_review_required"}
    assert any("manual" in row["suggested_review_action"] for row in rows)
    assert any(row["review_status"] == "review_required" for row in rows)


def test_boundary_only_category_filter_keeps_blocked_terms_in_boundary_context() -> None:
    payload = _payload()
    view = presenter.build_followup_queue_filter_view(
        payload["followup_queue_section"],
        followup_type="boundary_only_category",
    )

    assert view["selected_followup_type"] == "boundary_only_category"
    assert view["group_counts"] == {"boundary_only_category": 3}
    assert {row["followup_type"] for row in view["rows"]} == {"boundary_only_category"}
    assert payload["boundary_section"]["blocked_output_categories"] == [
        "final_biological_solution",
        "protocol",
        "yield_prediction",
    ]
    assert "yield_prediction" not in str(view["rows"])


def test_empty_followup_queue_filter_state_is_safe_and_readable() -> None:
    payload = presenter.build_plant_evidence_review_worksheet_payload()
    view = presenter.build_followup_queue_filter_view(
        payload["followup_queue_section"],
        followup_type="missing_provenance",
    )

    assert view["read_only"] is True
    assert view["selected_followup_type"] == presenter.ALL_FOLLOWUP_TYPES_FILTER
    assert view["followup_type_options"] == []
    assert view["rows"] == []
    assert view["grouped_rows"] == {}
    assert view["empty_state"] == "No worksheet follow-up queue items are available yet."


def test_followup_filter_view_does_not_mutate_source_payload() -> None:
    payload = _payload(evidence_slot_match_result=_evidence_slot_result(missing_source=True, weak=True))
    source_section = payload["followup_queue_section"]
    before = [dict(row) for row in source_section["rows"]]

    view = presenter.build_followup_queue_filter_view(
        source_section,
        followup_type="weak_or_unreviewed_evidence",
        group_by_type=False,
    )
    view["rows"][0]["followup_type"] = "changed_in_view_only"

    assert source_section["rows"] == before
    assert payload["followup_queue_section"]["rows"] == before


def test_followup_filter_view_copy_has_no_ranking_recommendation_or_wet_lab_ready_wording() -> None:
    payload = _payload(evidence_slot_match_result=_evidence_slot_result(missing_source=True, weak=True))
    view = presenter.build_followup_queue_filter_view(payload["followup_queue_section"])
    text = str(view).casefold()

    for phrase in ("rank", "recommended component", "wet-lab ready", "experiment-ready", "production-ready"):
        assert phrase not in text
    assert "read-only documentation-review" in text


def test_component_slot_linkage_links_evidence_to_component() -> None:
    payload = _payload()
    evidence_row = payload["evidence_review_section"]["rows"][0]
    component_row = payload["component_slot_linkage_section"]["rows"][0]

    assert evidence_row["linked_slot_id"] == "promoter_slot"
    assert evidence_row["linked_component_id"] == "COMP-PROMOTER-RICE"
    assert evidence_row["linked_component_label"] == "Rice seed promoter component record"
    assert component_row["linked_evidence_ids"] == ["EV-PROMOTER"]
    assert component_row["linked_slot_label"] == "Promoter and leader"


def test_empty_input_returns_safe_payload() -> None:
    payload = presenter.build_plant_evidence_review_worksheet_payload()

    assert payload["worksheet_status"] == presenter.EMPTY_WORKSHEET_STATUS
    assert payload["summary"]["empty_input"] is True
    assert payload["summary"]["total_evidence_rows"] == 0
    assert payload["summary"]["linked_component_slot_count"] == 0
    assert payload["summary"]["missing_source_or_provenance_count"] == 0
    assert payload["summary"]["weak_or_unreviewed_evidence_count"] == 0
    assert payload["summary"]["manual_review_required_count"] == 0
    assert payload["summary"]["overall_review_state"] == presenter.OVERALL_STATE_EVIDENCE_INCOMPLETE
    assert payload["manual_review_required"] is True
    assert payload["evidence_review_section"]["rows"] == []
    assert payload["component_slot_linkage_section"]["rows"] == []
    assert payload["manual_review_section"]["rows"] == []
    assert payload["followup_queue_section"]["rows"] == []
    assert payload["summary"]["followup_queue_count"] == 0
    assert payload["warnings"] == ["worksheet input warning: no readable plant review evidence payload was provided"]


def test_manual_review_required_state_keeps_review_items() -> None:
    payload = _payload()
    row = payload["manual_review_section"]["rows"][0]

    assert row["item_id"] == "r72-001-provenance-gap-promoter"
    assert row["category"] == "provenance_gap"
    assert row["severity"] == "review_required"
    assert row["linked_slot_id"] == "promoter_slot"
    assert row["linked_component_ids"] == ["COMP-PROMOTER-RICE"]
    assert row["linked_evidence_ids"] == ["EV-PROMOTER"]
    assert "manual_review_required" in row["gap_reason"]
    assert payload["summary"]["manual_review_required_count"] == 3
    followups = payload["followup_queue_section"]["rows"]
    assert any(
        followup["followup_type"] == "manual_review_required"
        and followup["linked_evidence_id"] == "EV-PROMOTER"
        for followup in followups
    )


def test_component_slot_linkage_gap_creates_followup_row() -> None:
    payload = _payload(component_candidate_match_result=_component_candidate_result(linkage_gap=True))
    followups = payload["followup_queue_section"]["rows"]

    assert any(
        row["followup_type"] == "component_slot_linkage_gap"
        and row["linked_component"] == "COMP-PROMOTER-RICE"
        and row["linked_slot"] == "promoter_slot"
        and row["suggested_review_action"] == "clarify linked component slot and evidence traceability"
        for row in followups
    )


def test_blocked_boundary_categories_are_preserved_as_categories_only() -> None:
    payload = _payload()

    assert payload["boundary_section"]["blocked_output_categories"] == [
        "final_biological_solution",
        "protocol",
        "yield_prediction",
    ]
    assert payload["summary"]["blocked_boundary_category_count"] == 3
    assert payload["summary"]["followup_queue_type_counts"]["boundary_only_category"] == 3
    assert any(
        row["followup_type"] == "boundary_only_category"
        and row["review_status"] == "boundary_only"
        and row["reason"] == "blocked output boundary category recorded for manual review"
        for row in payload["followup_queue_section"]["rows"]
    )
    assert payload["boundary_section"]["allowed_output_categories"] == [
        "documentation_readback",
        "evidence_gap_review",
        "component_slot_traceability",
        "manual_review_status",
    ]
    assert "yield prediction" not in str(payload["evidence_review_section"]).casefold()


def test_deterministic_stable_keys_and_order() -> None:
    first = _payload()
    second = _payload()

    assert first == second
    assert first["stable_keys"]["evidence_review_row_keys"] == list(presenter.EVIDENCE_REVIEW_COLUMNS)
    assert first["stable_keys"]["component_slot_row_keys"] == list(presenter.COMPONENT_SLOT_COLUMNS)
    assert first["stable_keys"]["manual_review_row_keys"] == list(presenter.MANUAL_REVIEW_COLUMNS)
    assert first["stable_keys"]["followup_queue_row_keys"] == list(presenter.FOLLOWUP_QUEUE_COLUMNS)
    assert all(set(row) == set(presenter.FOLLOWUP_QUEUE_COLUMNS) for row in first["followup_queue_section"]["rows"])
    assert first["evidence_review_section"]["rows"][0]["row_id"] == (
        "r118-evidence-001-promoter_slot-ev_promoter-comp_promoter_rice"
    )
    assert first["component_slot_linkage_section"]["rows"][0]["row_id"] == (
        "r118-component-slot-001-promoter_slot-comp_promoter_rice"
    )
    assert first["followup_queue_section"]["rows"][0]["followup_id"].startswith("r122-followup-001-")


def test_direct_placeholder_inputs_are_supported() -> None:
    payload = presenter.build_plant_evidence_review_worksheet_payload(
        source_payload={
            "route_context": _route_context(),
            "evidence_placeholders": [
                {
                    "evidence_id": "EV-DIRECT",
                    "title": "Direct plant evidence placeholder",
                    "source_type": "local note",
                    "source_status": "unreviewed",
                    "slot_id": "cds_label",
                    "manual_review_note": "Needs source follow-up.",
                }
            ],
            "component_slots": [
                {
                    "component_id": "COMP-CDS",
                    "component_name": "CDS source component placeholder",
                    "component_type": "cds_source",
                    "slot_id": "cds_label",
                    "matched_evidence_ids": ["EV-DIRECT"],
                    "provenance_status": "source_provenance_missing",
                }
            ],
            "review_items": [
                {
                    "item_id": "manual-direct-001",
                    "category": "evidence_gap",
                    "severity": "review_required",
                    "slot_id": "cds_label",
                    "evidence_ids": ["EV-DIRECT"],
                    "note": "Direct placeholder needs manual review.",
                }
            ],
        }
    )
    row = payload["evidence_review_section"]["rows"][0]

    assert row["evidence_item_id"] == "EV-DIRECT"
    assert row["linked_component_id"] == "COMP-CDS"
    assert row["linked_slot_id"] == "cds_label"
    assert payload["manual_review_section"]["rows"][0]["item_id"] == "manual-direct-001"


def test_presenter_source_and_output_do_not_add_forbidden_positive_copy() -> None:
    payload = _payload()
    generated = dict(payload)
    generated["boundary_section"] = {}
    text = str(generated).casefold()
    source_text = Path("services/plant_evidence_review_worksheet_presenter.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text
        assert phrase not in source_text

    assert "documentation-only" in text
    assert "manual review" in text
