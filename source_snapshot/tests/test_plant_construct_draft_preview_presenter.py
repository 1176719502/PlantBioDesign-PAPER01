# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_construct_draft_preview_presenter as presenter_service
from services import plant_construct_draft_readback_adapter as readback_service
from services import plant_construct_draft_readback_preview_adapter as preview_service
from services import plant_construct_task_draft_builder as draft_service
from services import plant_goal_route_generator as route_service
from services import plant_route_construct_task_bridge as bridge_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("best ", "route"),
    _term("correct ", "route"),
    _term("valid", "ated"),
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("proto", "col"),
    _term("opti", "mized"),
    _term("yield ", "pre", "diction"),
    _term("expression ", "pre", "diction"),
    _term("guaranteed ", "expression"),
    _term("experiment", "-ready"),
)


def _allowed_route() -> dict[str, object]:
    return {
        "plant_goal": "Plant protein expression review",
        "matched_goal_type_id": "plant_molecular_farming_protein_expression",
        "route_generation_status": route_service.ROUTE_GENERATION_ALLOWED,
        "manual_review_required": True,
        "candidate_route": {
            "route_id": "protein-route-candidate",
            "route_framing": "case-supported option",
            "supporting_source_ids": ["SRC-PROTEIN-001"],
            "required_component_slots": [
                "plant_context",
                "target_product",
                "promoter",
                "terminator",
                "marker",
                "vector",
            ],
            "slot_source_ids": {
                "plant_species": ["SRC-PLANT-001"],
                "cds": ["SRC-CDS-001"],
                "promoter": ["SRC-PROMOTER-001"],
                "terminator": ["SRC-TERM-001"],
                "marker": ["SRC-MARKER-001"],
                "vector": ["SRC-VECTOR-001"],
            },
            "missing_fields": [],
            "manual_review_required": True,
        },
    }


def _readback_payload() -> dict[str, object]:
    task_result = bridge_service.build_plant_construct_task_requirements(_allowed_route())
    task_result["goal_type"] = "plant_molecular_farming_protein_expression"
    task_result["route_type"] = "case-supported option"
    draft = draft_service.build_plant_construct_task_draft(task_result)
    return readback_service.build_plant_construct_draft_readback(draft)


def _preview_payload() -> dict[str, object]:
    readback = _readback_payload()
    preview = preview_service.build_plant_construct_draft_readback_preview(readback)
    preview["draft_id"] = readback["draft_id"]
    preview["draft_status"] = readback["draft_status"]
    preview["manual_review_required"] = readback["manual_review_required"]
    preview["safety_boundary"] = readback["safety_boundary"]
    preview["review_items"] = readback["review_items"]
    return preview


def _slot_map(presenter: dict[str, object]) -> dict[str, dict[str, object]]:
    table = presenter["slot_table"]  # type: ignore[index]
    return {row["slot_name"]: row for row in table["rows"]}  # type: ignore[index]


def test_basic_r332_preview_presenter_returns_core_sections_and_preserves_status() -> None:
    preview = _preview_payload()

    presenter = presenter_service.build_plant_construct_draft_preview_presenter(preview)

    assert presenter["status"] == presenter_service.PRESENTER_STATUS_AVAILABLE
    assert presenter["page_title"] == "Plant Construct Draft Preview"
    assert presenter["subtitle"] == "UI-safe presenter for read-only construct draft review."
    assert "draft_summary_card" in presenter
    assert "status_badges" in presenter
    assert "slot_table" in presenter
    assert presenter["draft_summary_card"]["draft_id"] == "construct-draft-protein-route-candidate"  # type: ignore[index]
    assert presenter["draft_summary_card"]["draft_status"] == draft_service.DRAFT_STATUS_NEEDS_MANUAL_REVIEW  # type: ignore[index]
    assert presenter["draft_summary_card"]["manual_review_required"] is True  # type: ignore[index]

    second = presenter_service.build_plant_construct_draft_preview_presenter(preview)
    assert presenter == second


def test_slot_table_preserves_required_rows_statuses_reasons_and_ids() -> None:
    presenter = presenter_service.build_plant_construct_draft_preview_presenter(_preview_payload())
    by_slot = _slot_map(presenter)

    assert {
        "promoter",
        "cds_payload_gene_or_enzyme",
        "terminator",
        "selectable_marker",
        "vector_backbone",
    } <= set(by_slot)
    assert by_slot["promoter"]["status"] == draft_service.SLOT_STATUS_NEEDS_CONFIRMATION
    assert by_slot["promoter"]["safe_status_text"] == "needs confirmation; manual review required"
    assert by_slot["promoter"]["missing_reason"] == preview_service.NOT_PROVIDED
    assert by_slot["promoter"]["evidence_ids"] == ["SRC-PROMOTER-001"]
    assert by_slot["cds_payload_gene_or_enzyme"]["evidence_ids"] == ["SRC-CDS-001"]
    assert by_slot["vector_backbone"]["evidence_ids"] == ["SRC-VECTOR-001"]
    assert by_slot["promoter"]["manual_review_required"] is True


def test_missing_fields_section_preserves_reasons_and_manual_review_visibility() -> None:
    payload = _preview_payload()
    payload["slot_rows"] = [
        {
            "slot_name": "promoter",
            "display_label": "Promoter",
            "role": "regulatory slot",
            "status": "needs_source",
            "safe_status_text": "missing source; manual review required",
            "value": "",
            "source_ids": [],
            "evidence_ids": [],
            "missing_reason": "promoter source evidence not provided",
            "manual_review_required": True,
        },
        {
            "slot_name": "vector_backbone",
            "display_label": "Vector backbone",
            "role": "vector backbone slot",
            "status": "missing",
            "safe_status_text": "missing required slot; manual review required",
            "value": "",
            "source_ids": [],
            "evidence_ids": ["SRC-VECTOR-GAP"],
            "missing_reason": "vector source evidence not provided",
            "manual_review_required": True,
        },
    ]
    payload["review_counts"] = {
        "slot_count": 2,
        "present_slot_count": 0,
        "missing_slot_count": 1,
        "needs_source_count": 1,
        "needs_confirmation_count": 0,
        "warning_count": 0,
        "review_item_count": 2,
    }

    presenter = presenter_service.build_plant_construct_draft_preview_presenter(payload)
    missing_rows = presenter["missing_fields_section"]["rows"]  # type: ignore[index]

    assert len(missing_rows) == 2
    assert missing_rows[0]["missing_reason"] == "promoter source evidence not provided"
    assert missing_rows[1]["missing_reason"] == "vector source evidence not provided"
    assert presenter["missing_fields_section"]["manual_review_required"] is True  # type: ignore[index]
    assert presenter["draft_summary_card"]["manual_review_required"] is True  # type: ignore[index]


def test_evidence_summary_aggregates_ids_without_inventing_evidence() -> None:
    presenter = presenter_service.build_plant_construct_draft_preview_presenter(_preview_payload())
    evidence_summary = presenter["evidence_summary"]  # type: ignore[index]

    assert "SRC-PROMOTER-001" in evidence_summary["evidence_ids"]
    assert "SRC-CDS-001" in evidence_summary["evidence_ids"]
    assert "SRC-VECTOR-001" in evidence_summary["evidence_ids"]
    assert "SRC-NOT-SUPPLIED" not in evidence_summary["evidence_ids"]
    assert evidence_summary["source_ids"] == []
    assert evidence_summary["note"] == "Identifiers are displayed as supplied; no evidence is inferred."


def test_invalid_or_blocked_preview_returns_safe_empty_state_without_crashing() -> None:
    invalid = presenter_service.build_plant_construct_draft_preview_presenter(None)
    empty = presenter_service.build_plant_construct_draft_preview_presenter({})
    blocked_preview = preview_service.build_plant_construct_draft_readback_preview(
        {
            "readback_status": readback_service.READBACK_STATUS_EMPTY,
            "draft_status": "route_generation_blocked",
            "warnings": ["Construct draft input is blocked; no slot readback is available."],
            "slot_rows": [],
        }
    )
    blocked = presenter_service.build_plant_construct_draft_preview_presenter(blocked_preview)

    for presenter in [invalid, empty, blocked]:
        assert presenter["status"] == presenter_service.PRESENTER_STATUS_EMPTY
        assert presenter["empty_state"]["is_empty"] is True  # type: ignore[index]
        assert presenter["slot_table"]["rows"] == []  # type: ignore[index]
        assert presenter["draft_summary_card"]["manual_review_required"] is True  # type: ignore[index]
    assert blocked["warnings_section"]["warnings"] == ["Construct draft input is blocked; no slot readback is available."]  # type: ignore[index]


def test_presenter_output_and_service_copy_avoid_unsafe_claims() -> None:
    presenter = presenter_service.build_plant_construct_draft_preview_presenter(_preview_payload())
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_construct_draft_preview_presenter.py"
    ).read_text(encoding="utf-8")
    output_text = str(presenter)

    for text in [output_text, service_text]:
        lowered = text.casefold()
        for forbidden in FORBIDDEN_WORDING:
            assert forbidden not in lowered


def test_r332_compatibility_accepts_actual_preview_payload_shape() -> None:
    actual_r332_preview = preview_service.build_plant_construct_draft_readback_preview(_readback_payload())

    presenter = presenter_service.build_plant_construct_draft_preview_presenter(actual_r332_preview)

    assert presenter["status"] == presenter_service.PRESENTER_STATUS_AVAILABLE
    assert presenter["slot_table"]["row_count"] == len(actual_r332_preview["slot_rows"])  # type: ignore[index]
    assert presenter["draft_summary_card"]["draft_id"] == ""  # type: ignore[index]
    assert presenter["draft_summary_card"]["draft_status"] == presenter_service.NOT_PROVIDED  # type: ignore[index]
    assert presenter["draft_summary_card"]["review_counts"] == actual_r332_preview["review_counts"]  # type: ignore[index]
