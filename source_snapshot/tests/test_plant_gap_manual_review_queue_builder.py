# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

from services import evidence_record_normalizer as normalizer
from services import plant_component_candidate_matcher
from services import plant_evidence_slot_matcher
from services import plant_gap_manual_review_queue_builder as queue_builder
from services import plant_user_intent_route_draft_builder as draft_builder


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


def _rice_albumin_draft() -> dict[str, Any]:
    return draft_builder.build_plant_expression_route_draft(
        {
            "target_name": "rice albumin",
            "plant_host": "Oryza sativa rice",
            "plant_context": "rice seed expression context",
            "expression_purpose": "local documentation review",
            "known_cds_source": "OsAlbumin CDS source note",
            "known_vector_or_backbone": "plant binary vector source note",
            "known_component_ids": {
                "promoter": "rice seed promoter source note",
                "terminator": "rice terminator source note",
            },
            "evidence_sources": ["local rice albumin evidence set"],
        }
    )


def _evidence_records(include_cds: bool = True) -> list[dict[str, Any]]:
    raw_records: list[dict[str, Any]] = [
        {
            "id": "EV-PROMOTER",
            "paper_title": "Rice seed promoter source metadata",
            "summary": "Local note for an Oryza sativa seed promoter used as plant regulatory source context.",
            "publication_year": "2024",
            "journal": "Local citation index",
            "PMID": "100001",
            "tags": "rice, seed, promoter, plant",
            "design_context": {"promoter": "rice seed promoter"},
            "provenance_note": "Curated local source metadata.",
        },
        {
            "id": "EV-TERMINATOR",
            "paper_title": "Plant terminator source metadata",
            "summary": "Local note for a plant terminator and polyadenylation source context.",
            "publication_year": "2022",
            "journal": "Local citation index",
            "PMID": "100003",
            "tags": "rice, terminator, plant",
            "design_context": {"terminator": "plant terminator"},
            "provenance_note": "Curated local source metadata.",
        },
    ]
    if include_cds:
        raw_records.append(
            {
                "id": "EV-CDS",
                "paper_title": "Rice albumin CDS identity source metadata",
                "summary": "Local source note for rice albumin coding sequence and protein identity.",
                "publication_year": "2023",
                "journal": "Local citation index",
                "PMID": "100002",
                "tags": "rice, albumin, cds, coding sequence, plant",
                "design_context": {"target_product": "rice albumin"},
                "provenance_note": "Curated local source metadata.",
            }
        )
    return normalizer.normalize_evidence_records(raw_records)


def _component_records(include_cds: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = [
        {
            "component_id": "COMP-PROMOTER-RICE",
            "component_name": "Rice seed promoter component record",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "Oryza sativa rice seed expression context",
            "aliases": ["rice seed promoter source note"],
            "matched_evidence_ids": ["EV-PROMOTER"],
            "source_label": "local promoter source record",
            "source_reference": "EV-PROMOTER",
            "provenance_status": "source provenance recorded",
            "provenance_note": "Curated local component source metadata.",
        },
        {
            "component_id": "COMP-TERM-RICE",
            "component_name": "Plant terminator component record",
            "component_type": "terminator",
            "design_slot_tags": ["terminator_slot"],
            "plant_context": "rice seed expression context",
            "matched_evidence_ids": ["EV-TERMINATOR"],
            "source_label": "local terminator source record",
            "source_reference": "EV-TERMINATOR",
            "provenance_status": "source provenance recorded",
            "provenance_note": "Curated local component source metadata.",
        },
    ]
    if include_cds:
        records.append(
            {
                "component_id": "COMP-CDS-ALBUMIN",
                "component_name": "Rice albumin CDS source component record",
                "component_type": "cds_source",
                "design_slot_tags": ["cds_label", "coding_sequence_slot"],
                "plant_context": "Oryza sativa rice",
                "aliases": ["OsAlbumin CDS source note", "rice albumin"],
                "matched_evidence_ids": ["EV-CDS"],
                "source_label": "local CDS source record",
                "source_reference": "EV-CDS",
                "provenance_status": "source provenance recorded",
                "provenance_note": "Curated local component source metadata.",
            }
        )
    return records


def _chain(
    evidence_records: list[dict[str, Any]],
    component_records: list[dict[str, Any]],
) -> dict[str, Any]:
    draft = _rice_albumin_draft()
    evidence_result = plant_evidence_slot_matcher.match_plant_evidence_to_slots(
        draft,
        evidence_records,
        {"query": "rice albumin seed expression evidence"},
    )
    component_result = plant_component_candidate_matcher.match_plant_component_candidates(
        draft,
        evidence_result,
        component_records,
        {"query": "rice albumin seed expression component review"},
    )
    return queue_builder.build_plant_gap_manual_review_queue(
        draft,
        evidence_result,
        component_result,
        {"batch": "R72"},
    )


def _items_by_category(result: dict[str, Any], category: str) -> list[dict[str, Any]]:
    return [item for item in result["review_items"] if item["category"] == category]


def test_rice_albumin_missing_cds_evidence_adds_evidence_gap_without_promoter_gap() -> None:
    draft = _rice_albumin_draft()
    evidence_result = {
        "manual_review_required": True,
        "manual_review_reasons": ["manual_review_required"],
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_status": "candidate_evidence_manual_review",
                "candidate_evidence": [{"record_id": "EV-PROMOTER"}],
                "manual_review_reasons": ["manual_review_required"],
            },
            {
                "slot_id": "cds_label",
                "slot_status": "missing_evidence",
                "candidate_evidence": [],
                "manual_review_reasons": ["manual_review_required", "missing_slot_evidence"],
            },
        ],
    }
    component_result = {
        "manual_review_required": True,
        "manual_review_reasons": ["manual_review_required"],
        "slots": [
            {
                "slot_id": "promoter_slot",
                "slot_status": "component_candidates_for_manual_review",
                "matched_evidence_ids": ["EV-PROMOTER"],
                "candidate_components": [
                    {
                        "component_id": "COMP-PROMOTER-RICE",
                        "matched_evidence_ids": ["EV-PROMOTER"],
                        "source_completeness": {"has_source": True, "has_provenance": True},
                    }
                ],
            }
        ],
    }
    result = queue_builder.build_plant_gap_manual_review_queue(draft, evidence_result, component_result)

    evidence_gaps = _items_by_category(result, queue_builder.CATEGORY_EVIDENCE_GAP)
    promoter_gaps = [item for item in evidence_gaps if item["slot_id"] == "promoter_slot"]
    cds_gaps = [item for item in evidence_gaps if item["slot_id"] in {"cds_label", "coding_sequence_slot"}]

    assert result["queue_status"] == queue_builder.QUEUE_STATUS_SUPPORTED
    assert result["manual_review_required"] is True
    assert result["final_design_present"] is False
    assert result["active_component_selection"] is False
    assert cds_gaps
    assert promoter_gaps == []
    assert result["summary"]["evidence_gap_count"] >= len(cds_gaps)


def test_slot_with_evidence_but_no_component_candidate_adds_component_gap_with_evidence_ids() -> None:
    draft = _rice_albumin_draft()
    evidence_result = {
        "manual_review_required": True,
        "manual_review_reasons": ["manual_review_required"],
        "slots": [
            {
                "slot_id": "cds_label",
                "slot_status": "candidate_evidence_manual_review",
                "candidate_evidence": [{"record_id": "EV-CDS"}],
                "manual_review_reasons": ["manual_review_required"],
            }
        ],
    }
    component_result = {
        "manual_review_required": True,
        "manual_review_reasons": ["manual_review_required", "missing_component_candidate"],
        "slots": [
            {
                "slot_id": "cds_label",
                "slot_status": "missing_component_candidate",
                "matched_evidence_ids": ["EV-CDS"],
                "candidate_components": [],
                "manual_review_reasons": ["manual_review_required", "missing_component_candidate"],
            }
        ],
    }
    result = queue_builder.build_plant_gap_manual_review_queue(draft, evidence_result, component_result)

    component_gaps = _items_by_category(result, queue_builder.CATEGORY_COMPONENT_GAP)
    cds_component_gaps = [
        item
        for item in component_gaps
        if item["slot_id"] == "cds_label"
    ]

    assert cds_component_gaps
    assert all("EV-CDS" in item["evidence_ids"] for item in cds_component_gaps)
    assert all(item["severity"] == queue_builder.SEVERITY_REVIEW_REQUIRED for item in cds_component_gaps)


def test_component_candidate_missing_provenance_is_retained_as_review_item() -> None:
    records = [
        {
            "component_id": "COMP-PROMOTER-MISSING-SOURCE",
            "component_name": "Rice promoter component record needing source follow-up",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "rice seed expression context",
        }
    ]
    result = _chain(_evidence_records(include_cds=False), records)
    provenance_gaps = _items_by_category(result, queue_builder.CATEGORY_PROVENANCE_GAP)

    assert any(
        item["slot_id"] == "promoter_slot"
        and item["component_ids"] == ["COMP-PROMOTER-MISSING-SOURCE"]
        for item in provenance_gaps
    )
    assert "final_component" not in str(result).casefold()
    assert "selected_component" not in str(result).casefold()


def test_duplicate_alias_candidates_add_ambiguity_review_without_auto_merge() -> None:
    records = [
        {
            "component_id": "COMP-PROMOTER-A",
            "component_name": "Shared rice promoter label",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "rice seed expression context",
            "aliases": ["shared promoter alias"],
            "matched_evidence_ids": ["EV-PROMOTER"],
            "source_label": "source A",
            "provenance_note": "local note A",
        },
        {
            "component_id": "COMP-PROMOTER-B",
            "component_name": "Shared rice promoter label",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "rice seed expression context",
            "aliases": ["shared promoter alias"],
            "matched_evidence_ids": ["EV-PROMOTER"],
            "source_label": "source B",
            "provenance_note": "local note B",
        },
    ]
    result = _chain(_evidence_records(include_cds=False), records)
    ambiguity_items = _items_by_category(result, queue_builder.CATEGORY_AMBIGUITY)

    assert [item["priority"] for item in result["review_items"]] == sorted(
        item["priority"] for item in result["review_items"]
    )
    assert {
        component_id
        for item in ambiguity_items
        for component_id in item["component_ids"]
    } == {"COMP-PROMOTER-A", "COMP-PROMOTER-B"}
    rendered = str(result).casefold()
    assert "auto-merged" in rendered
    assert "winner" not in rendered


def test_non_plant_unsupported_draft_adds_unsupported_scope_blocker() -> None:
    draft = draft_builder.build_plant_expression_route_draft("express GFP in E. coli")
    evidence_result = plant_evidence_slot_matcher.match_plant_evidence_to_slots(
        draft,
        _evidence_records(include_cds=True),
    )
    component_result = plant_component_candidate_matcher.match_plant_component_candidates(
        draft,
        evidence_result,
        _component_records(include_cds=True),
    )
    result = queue_builder.build_plant_gap_manual_review_queue(draft, evidence_result, component_result)

    assert result["queue_status"] == queue_builder.QUEUE_STATUS_UNSUPPORTED
    assert result["plant_scope_supported"] is False
    assert result["active_plant_design_route"] is False
    assert result["summary"]["blocker_count"] >= 1
    assert result["review_items"][0]["category"] == queue_builder.CATEGORY_UNSUPPORTED_SCOPE
    assert result["review_items"][0]["severity"] == queue_builder.SEVERITY_BLOCKER


def test_empty_input_fails_safe_with_route_context_gap_blocker() -> None:
    result = queue_builder.build_plant_gap_manual_review_queue({}, {}, [])

    assert result["queue_status"] == queue_builder.QUEUE_STATUS_FAIL_SAFE
    assert result["manual_review_required"] is True
    assert result["final_design_present"] is False
    assert result["summary"]["blocker_count"] >= 1
    assert result["review_items"][0]["category"] == queue_builder.CATEGORY_ROUTE_CONTEXT_GAP
    assert result["review_items"][0]["severity"] == queue_builder.SEVERITY_BLOCKER


def test_queue_output_is_plain_dict_list_string_bool_number_data() -> None:
    result = _chain(_evidence_records(include_cds=True), _component_records(include_cds=True))

    _assert_plain_data(result)


def test_queue_builder_stays_offline_ui_db_import_export_and_sequence_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant gap queue builder must stay local and offline")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = _chain(_evidence_records(include_cds=True), _component_records(include_cds=True))
    assert result["queue_status"] == queue_builder.QUEUE_STATUS_SUPPORTED
    importlib.reload(queue_builder)


def test_queue_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(_chain(_evidence_records(include_cds=True), _component_records(include_cds=True))).casefold()
    source_text = Path("services/plant_gap_manual_review_queue_builder.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "manual review" in result_text
