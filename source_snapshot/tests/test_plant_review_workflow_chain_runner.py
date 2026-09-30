# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path
from typing import Any

from services import plant_review_workflow_chain_runner as runner


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


def _intent() -> dict[str, Any]:
    return {
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


def _evidence_records() -> list[dict[str, Any]]:
    return [
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


def _run(
    *,
    intent: Any | None = None,
    evidence_records: Any | None = None,
    component_records: Any | None = None,
) -> dict[str, Any]:
    return runner.run_plant_review_workflow_chain(
        _intent() if intent is None else intent,
        _evidence_records() if evidence_records is None else evidence_records,
        _component_records() if component_records is None else component_records,
        {"query": "rice albumin seed expression review"},
        {"package_metadata": {"review_batch": "R76-test"}},
    )


def _slots_by_id(result: dict[str, Any], section: str) -> dict[str, dict[str, Any]]:
    return {slot["slot_id"]: slot for slot in result[section]["slots"]}


def _queue_categories(result: dict[str, Any]) -> set[str]:
    return {item["category"] for item in result["gap_manual_review_queue_result"]["review_items"]}


def test_coherent_plant_inputs_run_r68_to_r75_and_preserve_readback_sections() -> None:
    result = _run()

    assert result["chain_schema_version"] == runner.CHAIN_SCHEMA_VERSION
    assert result["route_draft"]["route_id"]
    assert result["evidence_slot_match_result"]["candidate_slot_evidence_present"] is True
    assert result["component_candidate_match_result"]["candidate_component_matches_present"] is True
    assert result["gap_manual_review_queue_result"]["review_items"]
    assert result["plant_review_package"]["package_type"] == "plant_review_package"
    assert result["readback_presenter"]["presenter_schema_version"]
    assert result["readback_presenter"]["construct_slot_section"]["rows"]
    assert result["readback_presenter"]["evidence_section"]["rows"]
    assert result["readback_presenter"]["component_candidate_section"]["rows"]
    assert result["traceability"]["source_payloads_present"]["readback_presenter"] is True
    assert result == _run()


def test_missing_evidence_completes_chain_and_flows_to_downstream_gap_review() -> None:
    result = _run(evidence_records=[])

    assert result["manual_review_required"] is True
    assert result["evidence_slot_match_result"]["candidate_slot_evidence_present"] is False
    assert result["plant_review_package"]["evidence_summary"]["evidence_gap_count"] > 0
    assert "evidence_gap" in _queue_categories(result)
    assert result["readback_presenter"]["gap_manual_review_section"]["counts"]["evidence_gap"] > 0


def test_evidence_without_component_creates_component_gap_downstream() -> None:
    result = _run(component_records=[])

    assert result["manual_review_required"] is True
    assert result["component_candidate_match_result"]["candidate_component_matches_present"] is False
    assert result["plant_review_package"]["component_candidate_summary"]["component_gap_count"] > 0
    assert "component_gap" in _queue_categories(result)
    assert result["readback_presenter"]["gap_manual_review_section"]["counts"]["component_gap"] > 0


def test_component_missing_provenance_is_preserved_as_review_gap() -> None:
    records = [
        {
            "component_id": "COMP-PROMOTER-MISSING-SOURCE",
            "component_name": "Rice promoter component record needing source follow-up",
            "component_type": "promoter",
            "design_slot_tags": ["promoter_slot"],
            "plant_context": "rice seed expression context",
            "matched_evidence_ids": ["EV-PROMOTER"],
        }
    ]
    result = _run(component_records=records)
    promoter = _slots_by_id(result, "component_candidate_match_result")["promoter_slot"]

    assert promoter["candidate_components"][0]["component_id"] == "COMP-PROMOTER-MISSING-SOURCE"
    assert "missing_provenance_or_source" in promoter["candidate_components"][0]["manual_review_reasons"]
    assert "provenance_gap" in _queue_categories(result)
    assert result["plant_review_package"]["component_candidate_summary"]["provenance_gap_count"] >= 1
    assert result["readback_presenter"]["gap_manual_review_section"]["counts"]["provenance_gap"] >= 1


def test_duplicate_alias_components_create_ambiguity_review_without_auto_merge_or_choice() -> None:
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
    result = _run(component_records=records)
    promoter = _slots_by_id(result, "component_candidate_match_result")["promoter_slot"]
    rendered = str(result).casefold()

    assert [candidate["component_id"] for candidate in promoter["candidate_components"]] == [
        "COMP-PROMOTER-A",
        "COMP-PROMOTER-B",
    ]
    assert all(candidate["duplicate_or_alias_flag"] for candidate in promoter["candidate_components"])
    assert "ambiguity_or_duplicate_review" in _queue_categories(result)
    assert "final_component" not in rendered
    assert "selected_component" not in rendered
    assert "winner" not in rendered


def test_unsupported_non_plant_intent_blocks_active_scope_and_keeps_safe_readback() -> None:
    result = _run(intent="express GFP in E. coli", evidence_records=[], component_records=[])

    assert result["chain_status"] == "blocked"
    assert result["blocked"] is True
    assert result["manual_review_required"] is True
    assert result["route_draft"]["route_id"] == "unsupported_non_plant_expression_context"
    assert result["plant_review_package"]["package_status"] == "blocked"
    assert result["readback_presenter"]["status_summary_card"]["status_label"] == "blocked"
    assert result["readback_presenter"]["gap_manual_review_section"]["counts"]["unsupported_scope"] >= 1
    assert result["route_draft"]["active_design_route"] is False


def test_empty_and_malformed_input_returns_safe_partial_chain_without_crash() -> None:
    empty = runner.run_plant_review_workflow_chain({}, [], [])
    malformed = runner.run_plant_review_workflow_chain(["bad", object()], [object()], [object()])

    assert empty["manual_review_required"] is True
    assert empty["route_draft"]
    assert empty["readback_presenter"]["package_header"]["manual_review_required"] is True
    assert malformed["manual_review_required"] is True
    assert malformed["warnings"]
    assert malformed["traceability"]["input_summary"]["evidence_record_count"] == 0
    assert malformed["traceability"]["input_summary"]["component_record_count"] == 0


def test_runner_output_is_plain_dict_list_string_bool_number_data() -> None:
    _assert_plain_data(_run())


def test_runner_stays_offline_ui_db_import_export_and_sequence_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib", "sqlite3"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("plant review workflow chain runner must stay local and offline")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = _run()
    assert result["route_draft"]
    importlib.reload(runner)


def test_runner_source_and_output_do_not_add_unsafe_claim_copy() -> None:
    result_text = str(_run()).casefold()
    source_text = Path("services/plant_review_workflow_chain_runner.py").read_text(encoding="utf-8").casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in result_text
        assert phrase not in source_text

    assert "documentation-only" in result_text
    assert "manual review" in result_text
