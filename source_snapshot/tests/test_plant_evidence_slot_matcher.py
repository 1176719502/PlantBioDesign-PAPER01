# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

from services import evidence_record_normalizer as normalizer
from services import plant_evidence_slot_matcher as matcher
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


def _normalized_records() -> list[dict[str, Any]]:
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


def _slots_by_id(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slot["slot_id"]: slot for slot in result["slots"]}


def test_rice_albumin_route_matches_promoter_cds_and_terminator_candidates() -> None:
    result = matcher.match_plant_evidence_to_slots(
        _rice_albumin_draft(),
        _normalized_records(),
        {"query": "rice albumin seed expression evidence"},
    )
    slots = _slots_by_id(result)

    assert result["matcher_status"] == matcher.SUPPORTED_MATCHER_STATUS
    assert result["plant_scope_supported"] is True
    assert result["final_design_present"] is False
    assert result["active_plant_design_evidence_matches"] is False
    assert result["candidate_slot_evidence_present"] is True
    assert slots["promoter_slot"]["candidate_evidence"][0]["record_id"] == "EV-PROMOTER"
    assert slots["cds_label"]["candidate_evidence"][0]["record_id"] == "EV-CDS"
    assert slots["coding_sequence_slot"]["candidate_evidence"][0]["record_id"] == "EV-CDS"
    assert slots["terminator_slot"]["candidate_evidence"][0]["record_id"] == "EV-TERMINATOR"
    assert slots["promoter_slot"]["manual_review_required"] is True
    assert slots["promoter_slot"]["score_breakdown"]["r64_ranker_score"] > 0
    assert "manual_review_required" in result["manual_review_reasons"]


def test_route_with_no_evidence_marks_every_required_slot_missing() -> None:
    result = matcher.match_plant_evidence_to_slots(_rice_albumin_draft(), [])

    assert result["plant_scope_supported"] is True
    assert result["candidate_slot_evidence_present"] is False
    assert result["manual_review_required"] is True
    assert result["missing_context"] == ["evidence_context"]
    assert result["summary"]["slot_count"] > 0
    assert result["summary"]["slots_with_candidate_evidence"] == 0
    assert all(slot["slot_status"] == "missing_evidence" for slot in result["slots"])
    assert all(slot["missing_evidence_reason"] == "no_evidence_records_provided" for slot in result["slots"])
    assert all(slot["manual_review_required"] is True for slot in result["slots"])


def test_unsupported_non_plant_draft_returns_fail_safe_without_active_matches() -> None:
    draft = draft_builder.build_plant_expression_route_draft("express GFP in E. coli")
    result = matcher.match_plant_evidence_to_slots(draft, _normalized_records())

    assert result["matcher_status"] == matcher.UNSUPPORTED_MATCHER_STATUS
    assert result["plant_scope_supported"] is False
    assert result["final_design_present"] is False
    assert result["active_plant_design_evidence_matches"] is False
    assert result["candidate_slot_evidence_present"] is False
    assert result["slots"] == []
    assert "supported_plant_route_context" in result["missing_context"]
    assert result["route_context"]["route_id"] == "unsupported_non_plant_expression_context"


def test_empty_unknown_route_draft_lists_missing_route_slot_and_evidence_context() -> None:
    result = matcher.match_plant_evidence_to_slots({}, [])

    assert result["matcher_status"] == matcher.FAIL_SAFE_MATCHER_STATUS
    assert result["manual_review_required"] is True
    assert result["final_design_present"] is False
    assert result["slots"] == []
    assert result["missing_context"] == ["route_context", "slot_context", "evidence_context"]


def test_ambiguous_evidence_can_be_candidate_but_keeps_manual_review_reason() -> None:
    records = normalizer.normalize_evidence_records(
        [
            {
                "id": "EV-AMBIG",
                "paper_title": "Rice promoter and terminator source metadata",
                "summary": "Ambiguous local note mentions promoter and terminator context in one source record.",
                "publication_year": "2024",
                "journal": "Local citation index",
                "PMID": "100004",
                "tags": "rice, promoter, terminator, ambiguous",
                "design_context": ["promoter", "terminator"],
                "provenance_note": "Needs curator separation before use in documentation readback.",
            }
        ]
    )
    result = matcher.match_plant_evidence_to_slots(_rice_albumin_draft(), records)
    slots = _slots_by_id(result)

    promoter_candidate = slots["promoter_slot"]["candidate_evidence"][0]
    terminator_candidate = slots["terminator_slot"]["candidate_evidence"][0]

    assert promoter_candidate["record_id"] == "EV-AMBIG"
    assert terminator_candidate["record_id"] == "EV-AMBIG"
    assert "ambiguous_evidence_context" in promoter_candidate["manual_review_reasons"]
    assert "ambiguous_evidence_context" in slots["promoter_slot"]["manual_review_reasons"]
    assert result["summary"]["ambiguous_candidate_count"] >= 2


def test_matcher_output_is_plain_dict_list_string_bool_number_data() -> None:
    result = matcher.match_plant_evidence_to_slots(_rice_albumin_draft(), _normalized_records())

    _assert_plain_data(result)


def test_matcher_stays_offline_ui_db_import_export_and_sequence_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant evidence slot matcher must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = matcher.match_plant_evidence_to_slots(_rice_albumin_draft(), _normalized_records())
    assert result["plant_scope_supported"] is True
    importlib.reload(matcher)


def test_matcher_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(matcher.match_plant_evidence_to_slots(_rice_albumin_draft(), _normalized_records())).casefold()
    source_text = Path("services/plant_evidence_slot_matcher.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "manual review" in result_text
