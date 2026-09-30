# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from pathlib import Path

from services import plant_construct_draft_preview_presenter as presenter_service
from services import plant_construct_draft_readback_adapter as readback_service
from services import plant_construct_draft_readback_preview_adapter as preview_service
from services import plant_construct_task_draft_builder as draft_service
from services import plant_goal_route_generator as route_service
from services import plant_route_construct_task_bridge as bridge_service
from tests.helpers.fake_streamlit import FakeStreamlit
import views.plant_construct_draft_preview_section as section_view
import views.tool_typography as tool_typography


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("build", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("proto", "col"),
    _term("valid", "ated"),
    _term("best ", "route"),
    _term("correct ", "route"),
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


def _presenter_payload() -> dict[str, object]:
    readback = _readback_payload()
    preview = preview_service.build_plant_construct_draft_readback_preview(readback)
    preview["draft_id"] = readback["draft_id"]
    preview["draft_status"] = readback["draft_status"]
    preview["manual_review_required"] = readback["manual_review_required"]
    preview["safety_boundary"] = readback["safety_boundary"]
    preview["review_items"] = readback["review_items"]
    return presenter_service.build_plant_construct_draft_preview_presenter(preview)


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section_view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    dataframe_text = "\n".join(frame.to_string(index=False) for frame in fake_st.dataframes)
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + dataframe_text.splitlines()
    )


def test_ui_section_consumes_r333_presenter_payload_and_preserves_summary_status() -> None:
    section = section_view.build_plant_construct_draft_preview_section(_presenter_payload())

    assert section["status"] == section_view.SECTION_STATUS_AVAILABLE
    assert section["title"] == "Plant Construct Draft Preview"
    assert section["subtitle"] == "UI-safe presenter for read-only construct draft review."
    assert section["read_only"] is True
    assert section["summary"]["draft_id"] == "construct-draft-protein-route-candidate"
    assert section["summary"]["draft_status"] == draft_service.DRAFT_STATUS_NEEDS_MANUAL_REVIEW
    assert section["summary"]["manual_review_required"] == "yes"
    assert section["slot_table"].shape[0] >= 5
    assert section["status_badges"][1]["label"] == "Draft status"


def test_slot_table_display_preserves_required_rows_status_reasons_and_ids() -> None:
    section = section_view.build_plant_construct_draft_preview_section(_presenter_payload())
    slot_table = section["slot_table"]
    rows_by_key = {row["Slot key"]: row for row in slot_table.to_dict("records")}

    assert {
        "promoter",
        "cds_payload_gene_or_enzyme",
        "terminator",
        "selectable_marker",
        "vector_backbone",
    } <= set(rows_by_key)
    assert rows_by_key["promoter"]["Status"] == draft_service.SLOT_STATUS_NEEDS_CONFIRMATION
    assert rows_by_key["promoter"]["Source status"] == "needs confirmation; manual review required"
    assert rows_by_key["promoter"]["Missing reason"] == "not provided"
    assert rows_by_key["promoter"]["Evidence IDs"] == "SRC-PROMOTER-001"
    assert rows_by_key["cds_payload_gene_or_enzyme"]["Evidence IDs"] == "SRC-CDS-001"
    assert rows_by_key["vector_backbone"]["Evidence IDs"] == "SRC-VECTOR-001"
    assert rows_by_key["promoter"]["Manual review"] == "yes"


def test_missing_fields_review_items_and_manual_review_remain_visible() -> None:
    payload = _presenter_payload()
    payload["slot_table"]["rows"] = [
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
    payload["missing_fields_section"] = {
        "manual_review_required": True,
        "rows": [
            {
                "slot_name": "promoter",
                "display_label": "Promoter",
                "status": "needs_source",
                "missing_reason": "promoter source evidence not provided",
                "manual_review_required": True,
            },
            {
                "slot_name": "vector_backbone",
                "display_label": "Vector backbone",
                "status": "missing",
                "missing_reason": "vector source evidence not provided",
                "manual_review_required": True,
            },
        ],
    }
    payload["review_items_section"] = {
        "items": ["Promoter: missing source.", "Vector backbone: missing required slot."],
        "review_item_count": 2,
        "manual_review_required": True,
    }

    section = section_view.build_plant_construct_draft_preview_section(payload)
    missing_reasons = section["missing_fields"]["Missing reason"].tolist()

    assert "promoter source evidence not provided" in missing_reasons
    assert "vector source evidence not provided" in missing_reasons
    assert section["missing_fields"]["Manual review"].tolist() == ["yes", "yes"]
    assert "Promoter: missing source." in section["review_items"]["Review item"].tolist()
    assert section["summary"]["manual_review_required"] == "yes"


def test_invalid_or_blocked_payload_returns_safe_empty_state_without_crashing(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    blocked_preview = preview_service.build_plant_construct_draft_readback_preview(
        {
            "readback_status": readback_service.READBACK_STATUS_EMPTY,
            "draft_status": "route_generation_blocked",
            "warnings": ["Construct draft input is blocked; no slot readback is available."],
            "slot_rows": [],
        }
    )
    blocked_presenter = presenter_service.build_plant_construct_draft_preview_presenter(blocked_preview)

    invalid_section = section_view.build_plant_construct_draft_preview_section(None)
    rendered_section = section_view.render_plant_construct_draft_preview_section(blocked_presenter)
    rendered = _rendered_text(fake_st)

    assert invalid_section["status"] == section_view.SECTION_STATUS_EMPTY
    assert rendered_section["status"] == section_view.SECTION_STATUS_EMPTY
    assert rendered_section["empty_state"]["is_empty"] is True
    assert rendered_section["slot_table"].empty
    assert "Construct draft input is blocked; no slot readback is available." in rendered
    assert "No draft slot rows supplied." in rendered


def test_rendered_read_only_ui_contains_expected_sections_without_write_controls(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    section_view.render_plant_construct_draft_preview_section(_presenter_payload())
    rendered = _rendered_text(fake_st)

    assert "Plant Construct Draft Preview" in rendered
    assert "read-only construct draft review" in rendered
    assert "Status badges" in rendered
    assert "Draft slot table" in rendered
    assert "Evidence summary" in rendered
    assert "Missing fields" in rendered
    assert "Review items" in rendered
    assert "Warnings" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []


def test_ui_safety_boundary_copy_avoids_unsafe_claims() -> None:
    section = section_view.build_plant_construct_draft_preview_section(_presenter_payload())
    service_text = (
        Path(__file__).resolve().parents[1] / "views" / "plant_construct_draft_preview_section.py"
    ).read_text(encoding="utf-8")
    output_text = str(section)

    for text in [output_text, service_text]:
        lowered = text.casefold()
        for forbidden in FORBIDDEN_WORDING:
            assert forbidden not in lowered


def test_ui_section_does_not_add_write_export_or_sequence_generation_paths() -> None:
    source = inspect.getsource(section_view)
    forbidden_calls = [
        "download_button",
        "form_submit_button",
        "st.button",
        "repo.",
        "create_",
        "update_",
        "delete_",
        "fasta",
        "genbank",
        "concat",
        "codon",
    ]

    assert [call for call in forbidden_calls if call in source.casefold()] == []
