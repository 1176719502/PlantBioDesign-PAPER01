# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

from services import evidence_record_normalizer as normalizer
from services import plant_component_candidate_matcher as matcher
from services import plant_evidence_slot_matcher
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


def _evidence_records() -> list[dict[str, Any]]:
    return normalizer.normalize_evidence_records(
        [
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
                "id": "EV-CDS",
                "paper_title": "Rice albumin CDS identity source metadata",
                "summary": "Local source note for rice albumin coding sequence and protein identity.",
                "publication_year": "2023",
                "journal": "Local citation index",
                "PMID": "100002",
                "tags": "rice, albumin, cds, coding sequence, plant",
                "design_context": {"target_product": "rice albumin"},
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
    )


def _evidence_slot_result() -> dict[str, Any]:
    return plant_evidence_slot_matcher.match_plant_evidence_to_slots(
        _rice_albumin_draft(),
        _evidence_records(),
        {"query": "rice albumin seed expression evidence"},
    )


def _component_records() -> list[dict[str, Any]]:
    return [
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


def _slots_by_id(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slot["slot_id"]: slot for slot in result["slots"]}


def test_rice_albumin_route_matches_promoter_cds_and_terminator_review_candidates() -> None:
    result = matcher.match_plant_component_candidates(
        _rice_albumin_draft(),
        _evidence_slot_result(),
        _component_records(),
        {"query": "rice albumin seed expression component review"},
    )
    slots = _slots_by_id(result)

    assert result["matcher_status"] == matcher.SUPPORTED_MATCHER_STATUS
    assert result["plant_scope_supported"] is True
    assert result["final_design_present"] is False
    assert result["active_component_candidate_selection"] is False
    assert result["candidate_component_matches_present"] is True
    assert slots["promoter_slot"]["candidate_components"][0]["component_id"] == "COMP-PROMOTER-RICE"
    assert slots["cds_label"]["candidate_components"][0]["component_id"] == "COMP-CDS-ALBUMIN"
    assert slots["coding_sequence_slot"]["candidate_components"][0]["component_id"] == "COMP-CDS-ALBUMIN"
    assert slots["terminator_slot"]["candidate_components"][0]["component_id"] == "COMP-TERM-RICE"
    assert "EV-PROMOTER" in slots["promoter_slot"]["matched_evidence_ids"]
    assert slots["promoter_slot"]["candidate_components"][0]["matched_evidence_ids"] == ["EV-PROMOTER"]
    assert slots["promoter_slot"]["best_candidate_score"] > 0
    assert slots["promoter_slot"]["manual_review_required"] is True
    assert slots["backbone_label"]["manual_review_required"] is True
    assert slots["backbone_label"]["missing_component_reason"] == "no_component_record_matched_slot"


def test_component_with_matching_type_but_missing_provenance_remains_manual_review_candidate() -> None:
    records = [
        {
            "component_id": "COMP-PROMOTER-MISSING-SOURCE",
            "component_name": "Rice promoter component record needing source follow-up",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "rice seed expression context",
        }
    ]
    result = matcher.match_plant_component_candidates(_rice_albumin_draft(), _evidence_slot_result(), records)
    promoter = _slots_by_id(result)["promoter_slot"]
    candidate = promoter["candidate_components"][0]

    assert candidate["component_id"] == "COMP-PROMOTER-MISSING-SOURCE"
    assert candidate["source_completeness"]["completeness_score"] < 0.8
    assert candidate["manual_review_required"] is True
    assert "missing_provenance_or_source" in candidate["manual_review_reasons"]
    assert "missing_provenance_or_source" in promoter["manual_review_reasons"]


def test_duplicate_or_alias_like_component_records_are_flagged_without_final_choice() -> None:
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
    result = matcher.match_plant_component_candidates(_rice_albumin_draft(), _evidence_slot_result(), records)
    promoter = _slots_by_id(result)["promoter_slot"]
    rendered = str(result).casefold()

    assert [candidate["component_id"] for candidate in promoter["candidate_components"]] == [
        "COMP-PROMOTER-A",
        "COMP-PROMOTER-B",
    ]
    assert promoter["duplicate_or_alias_flag"] is True
    assert all(candidate["duplicate_or_alias_flag"] is True for candidate in promoter["candidate_components"])
    assert "final_component" not in rendered
    assert "selected_component" not in rendered
    assert "winner" not in rendered


def test_non_plant_unsupported_draft_returns_fail_safe_without_active_matches() -> None:
    draft = draft_builder.build_plant_expression_route_draft("express GFP in E. coli")
    evidence_result = plant_evidence_slot_matcher.match_plant_evidence_to_slots(draft, _evidence_records())
    result = matcher.match_plant_component_candidates(draft, evidence_result, _component_records())

    assert result["matcher_status"] == matcher.UNSUPPORTED_MATCHER_STATUS
    assert result["plant_scope_supported"] is False
    assert result["final_design_present"] is False
    assert result["active_component_candidate_selection"] is False
    assert result["candidate_component_matches_present"] is False
    assert result["slots"] == []
    assert "supported_plant_route_context" in result["missing_context"]
    assert result["route_context"]["route_id"] == "unsupported_non_plant_expression_context"


def test_empty_unknown_route_draft_lists_missing_route_slot_component_and_evidence_context() -> None:
    result = matcher.match_plant_component_candidates({}, {}, [])

    assert result["matcher_status"] == matcher.FAIL_SAFE_MATCHER_STATUS
    assert result["manual_review_required"] is True
    assert result["final_design_present"] is False
    assert result["slots"] == []
    assert result["missing_context"] == [
        "route_context",
        "slot_context",
        "evidence_slot_context",
        "component_context",
    ]


def test_non_plant_component_records_are_excluded_from_supported_plant_matching() -> None:
    records = [
        {
            "component_id": "COMP-ECOLI-PROMOTER",
            "component_name": "Bacterial promoter context record",
            "component_type": "promoter",
            "host_context": "E. coli bacterial host",
            "matched_evidence_ids": ["EV-PROMOTER"],
        }
    ]
    result = matcher.match_plant_component_candidates(_rice_albumin_draft(), _evidence_slot_result(), records)

    assert result["plant_scope_supported"] is True
    assert result["candidate_component_matches_present"] is False
    assert result["summary"]["out_of_scope_component_count"] == 1
    assert "out_of_scope_component_records" in result["manual_review_reasons"]


def test_matcher_output_is_plain_dict_list_string_bool_number_data() -> None:
    result = matcher.match_plant_component_candidates(
        _rice_albumin_draft(),
        _evidence_slot_result(),
        _component_records(),
    )

    _assert_plain_data(result)


def test_matcher_stays_offline_ui_db_import_export_and_sequence_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant component candidate matcher must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = matcher.match_plant_component_candidates(_rice_albumin_draft(), _evidence_slot_result(), _component_records())
    assert result["plant_scope_supported"] is True
    importlib.reload(matcher)


def test_matcher_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(
        matcher.match_plant_component_candidates(
            _rice_albumin_draft(),
            _evidence_slot_result(),
            _component_records(),
        )
    ).casefold()
    source_text = Path("services/plant_component_candidate_matcher.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "manual review" in result_text
