# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_construct_draft_readback_adapter as readback_service
from services import plant_construct_draft_readback_preview_adapter as preview_service
from services import plant_construct_task_draft_builder as draft_service
from services import plant_goal_route_generator as route_service
from services import plant_route_construct_task_bridge as bridge_service


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("ready"),
    _term("valid", "ated"),
    _term("approved"),
    _term("build", "-ready"),
    _term("experiment", "-ready"),
    _term("opti", "mized"),
    _term("recommended ", "construct"),
    _term("final ", "sequence"),
    _term("confirmed ", "expression"),
    _term("guaranteed ", "expression"),
    _term("proto", "col"),
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


def test_normal_incomplete_readback_payload_renders_stable_preview() -> None:
    preview = preview_service.build_plant_construct_draft_readback_preview(_readback_payload())

    assert preview["status"] == preview_service.PREVIEW_STATUS_AVAILABLE
    assert preview["is_empty"] is False
    assert preview["title"] == "Plant Construct Draft Readback Preview"
    assert "Documentation-only and manual-review-only preview" in preview["boundary_note"]
    assert "Manual review required." in preview["summary_lines"]
    assert preview["review_counts"]["slot_count"] == len(preview["slot_rows"])
    assert "# Plant Construct Draft Readback Preview" in preview["markdown"]
    assert "## Draft Slots" in preview["markdown"]

    second = preview_service.build_plant_construct_draft_readback_preview(_readback_payload())
    assert preview == second


def test_missing_slots_are_displayed_with_missing_reasons() -> None:
    payload = {
        "readback_status": readback_service.READBACK_STATUS_READY,
        "route_source_label": "case-supported option",
        "plant_host_or_context": "Nicotiana review context",
        "draft_status": "incomplete",
        "manual_review_required": True,
        "slot_rows": [
            {
                "slot_name": "promoter",
                "display_label": "Promoter",
                "role": "regulatory context",
                "status": "needs_source",
                "value": "",
                "missing_reason": "promoter source evidence not provided",
                "source_ids": [],
                "evidence_ids": [],
                "manual_review_required": True,
            },
            {
                "slot_name": "vector_backbone",
                "display_label": "Vector backbone",
                "role": "backbone context",
                "status": "missing",
                "value": "",
                "missing_reason": "vector context not provided",
                "source_ids": [],
                "evidence_ids": ["SRC-VECTOR-GAP"],
                "manual_review_required": True,
            },
        ],
        "warnings": ["One or more draft slots have missing source records."],
        "review_items": ["Promoter: missing source."],
    }

    preview = preview_service.build_plant_construct_draft_readback_preview(payload)

    assert preview["review_counts"]["missing_slot_count"] == 1
    assert preview["review_counts"]["needs_source_count"] == 1
    assert "Promoter: promoter source evidence not provided" in preview["missing_reason_lines"]
    assert "Vector backbone: vector context not provided" in preview["missing_reason_lines"]
    assert "promoter source evidence not provided" in preview["markdown"]
    assert "vector context not provided" in preview["markdown"]
    assert preview["slot_rows"][0]["recorded_value"] == "promoter source evidence not provided"


def test_source_ids_and_evidence_ids_are_preserved_as_identifiers_only() -> None:
    preview = preview_service.build_plant_construct_draft_readback_preview(_readback_payload())
    markdown = preview["markdown"]

    assert "SRC-PROMOTER-001" in markdown
    assert "SRC-CDS-001" in markdown
    assert "SRC-VECTOR-001" in markdown
    assert any(line.startswith("Evidence IDs:") for line in preview["source_reference_lines"])
    assert "strength" not in markdown.casefold()


def test_manual_review_required_state_and_warnings_are_propagated() -> None:
    payload = _readback_payload()
    payload["warnings"] = [
        "Incomplete construct draft: review missing slots and confirmation needs.",
        "One or more draft slots need confirmation.",
    ]

    preview = preview_service.build_plant_construct_draft_readback_preview(payload)

    assert "Manual review required." in preview["summary_lines"]
    assert preview["warning_lines"] == payload["warnings"]
    assert preview["review_counts"]["warning_count"] == 2
    assert "One or more draft slots need confirmation." in preview["markdown"]


def test_invalid_empty_and_blocked_payloads_return_safe_empty_preview() -> None:
    invalid = preview_service.build_plant_construct_draft_readback_preview(None)
    empty = preview_service.build_plant_construct_draft_readback_preview({})
    blocked = preview_service.build_plant_construct_draft_readback_preview(
        {
            "readback_status": readback_service.READBACK_STATUS_EMPTY,
            "draft_status": "route_generation_blocked",
            "warnings": ["Construct draft input is blocked; no slot readback is available."],
            "slot_rows": [],
        }
    )

    for preview in [invalid, empty, blocked]:
        assert preview["status"] == preview_service.PREVIEW_STATUS_EMPTY
        assert preview["is_empty"] is True
        assert preview["slot_rows"] == []
        assert "Manual review required." in preview["summary_lines"]
        assert "## Draft Slots" in preview["markdown"]
    assert blocked["warning_lines"] == ["Construct draft input is blocked; no slot readback is available."]


def test_preview_output_and_service_copy_avoid_unsafe_claims() -> None:
    preview = preview_service.build_plant_construct_draft_readback_preview(_readback_payload())
    service_text = (
        Path(__file__).resolve().parents[1] / "services" / "plant_construct_draft_readback_preview_adapter.py"
    ).read_text(encoding="utf-8")
    output_text = str(preview)

    for text in [output_text, service_text]:
        lowered = text.casefold()
        for forbidden in FORBIDDEN_WORDING:
            assert forbidden not in lowered


def test_markdown_rendering_is_deterministic_for_same_payload() -> None:
    payload = _readback_payload()

    first = preview_service.build_plant_construct_draft_readback_preview(payload)["markdown"]
    second = preview_service.build_plant_construct_draft_readback_preview(payload)["markdown"]

    assert first == second
    assert first.count("## Draft Slots") == 1
    assert first.count("| Slot | Role | Status |") == 1
