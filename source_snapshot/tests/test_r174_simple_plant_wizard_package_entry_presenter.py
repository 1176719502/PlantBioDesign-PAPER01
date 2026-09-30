# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.plant_simple_wizard_package_entry_presenter import (
    SAFE_PACKAGE_STATUSES,
    build_simple_plant_wizard_package_entry_presenter,
)
from services.plant_simple_wizard_route_checklist_presenter import (
    build_simple_plant_wizard_route_checklist_presenter,
)
from services.plant_simple_wizard_route_schema import ENTRY_ROUTE_IDS, HANDOFF_STAGE_ID
from views.pathway_workspace_sections import plant_review_workflow_section as section


PLAIN_TYPES = (dict, list, str, bool, int, float, type(None))


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_FRAGMENTS = (
    _term("valid", "ated"),
    _term("optim", "ized"),
    _term("experiment", "-ready"),
    _term("proto", "col"),
    _term("yield", " prediction"),
    _term("best", " component"),
    _term("wet", "-lab ready"),
    "ready",
    _term("final", " package"),
    _term("exported", " package"),
)


def _walk_plain_values(value: Any) -> None:
    assert isinstance(value, PLAIN_TYPES)
    if isinstance(value, dict):
        assert all(isinstance(key, str) for key in value)
        for item in value.values():
            _walk_plain_values(item)
    elif isinstance(value, list):
        for item in value:
            _walk_plain_values(item)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return "" if value is None else str(value)


def _payload(route_id: str = "plant_protein_expression_review", slot_records: Any = None) -> dict[str, Any]:
    checklist = build_simple_plant_wizard_route_checklist_presenter(route_id, slot_records)
    return build_simple_plant_wizard_package_entry_presenter(route_id, checklist)


def test_package_entry_resolves_all_entry_route_labels() -> None:
    for route_id in ENTRY_ROUTE_IDS:
        checklist = build_simple_plant_wizard_route_checklist_presenter(route_id)
        payload = build_simple_plant_wizard_package_entry_presenter(route_id, checklist)

        assert payload["route_id"] == route_id
        assert payload["route_label_zh"] == checklist["route_label_zh"]


def test_handoff_stage_is_shared_package_review_stage() -> None:
    payload = _payload()

    assert payload["package_stage_id"] == HANDOFF_STAGE_ID
    assert payload["package_stage_id"] == "plant_handoff_package_review"


def test_package_status_is_limited_to_safe_values() -> None:
    for route_id in ENTRY_ROUTE_IDS:
        assert _payload(route_id)["package_status"] in SAFE_PACKAGE_STATUSES


def test_empty_checklist_payload_produces_not_started_output() -> None:
    payload = build_simple_plant_wizard_package_entry_presenter("plant_protein_expression_review")

    assert payload["package_status"] == "not_started"
    assert payload["input_summary"]["total_slots"] == 0
    assert payload["gap_summary"]["summary_zh"]


def test_checklist_with_missing_fields_produces_incomplete_summary() -> None:
    payload = _payload(
        "plant_protein_expression_review",
        slot_records=[
            {"slot_id": "target_protein", "value": "albumin-like protein", "has_provenance": True},
            {"slot_id": "promoter", "status": "missing"},
            {"slot_id": "evidence_records", "status": "filled", "has_provenance": True},
            {"slot_id": "manual_review_status", "status": "filled"},
        ],
    )

    assert payload["package_status"] == "incomplete"
    assert payload["gap_summary"]["missing_field_count"] > 0
    assert "promoter" in payload["gap_summary"]["missing_field_slot_ids"]


def test_checklist_with_manual_review_items_produces_manual_review_summary() -> None:
    payload = _payload(
        "plant_metabolic_pathway_review",
        slot_records=[{"slot_id": "pathway_step", "status": "needs_manual_review"}],
    )

    assert payload["package_status"] == "needs_manual_review"
    assert payload["manual_review_summary"]["manual_review_item_count"] > 0
    assert "pathway_step" in payload["manual_review_summary"]["manual_review_slot_ids"]


def test_package_actions_are_mock_read_only_and_do_not_write_data() -> None:
    payload = _payload()

    assert payload["package_entry_actions"]
    for action in payload["package_entry_actions"]:
        assert action["is_mock"] is True
        assert action["does_not_write_data"] is True
        assert action["action_kind"].startswith("mock_")
        assert "save" not in action["action_id"]
        assert "export" not in action["action_id"]


def test_package_preview_sections_include_required_concepts() -> None:
    payload = _payload()
    section_blob = _text_blob(payload["package_preview_sections"]).casefold()

    for concept in ["route", "gap", "evidence", "manual", "handoff", "readback"]:
        assert concept in section_blob


def test_identity_preview_is_safe_placeholder_without_new_dependency() -> None:
    identity = _payload()["identity_preview"]

    assert identity["enabled"] is False
    assert identity["qr_status_zh"] == "未生成"
    assert identity["md5_status_zh"] == "未生成"
    assert identity["snapshot_status_zh"] == "未生成"
    assert identity["does_not_require_new_dependency"] is True


def test_payload_is_deterministic_across_repeated_calls() -> None:
    checklist = build_simple_plant_wizard_route_checklist_presenter(
        "plant_protein_expression_review",
        [{"slot_id": "host_plant", "value": "rice"}],
    )

    first = build_simple_plant_wizard_package_entry_presenter("plant_protein_expression_review", checklist)
    second = build_simple_plant_wizard_package_entry_presenter("plant_protein_expression_review", checklist)

    assert first == second


def test_payload_contains_only_plain_python_types() -> None:
    _walk_plain_values(_payload("plant_regulatory_module_review"))


def test_safety_copy_and_generated_text_do_not_contain_forbidden_claims() -> None:
    blob = _text_blob([_payload(route_id) for route_id in ENTRY_ROUTE_IDS]).casefold()

    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in blob


def test_ui_mount_renders_package_entry_without_action_buttons(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    checklist = build_simple_plant_wizard_route_checklist_presenter("plant_protein_expression_review")
    payload = section.render_simple_plant_wizard_package_entry_section(checklist_payload=checklist)
    rendered = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    assert payload["package_stage_id"] == HANDOFF_STAGE_ID
    assert "bds-simple-plant-wizard-package-entry" in rendered
    assert "Simple package preview sections" in rendered
    assert "Simple package mock actions" in rendered
    assert "Simple package identity preview" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_package_entry_mounts_after_checklist_before_advanced_detail() -> None:
    source = (
        Path(ROOT)
        / "views"
        / "pathway_workspace_sections"
        / "plant_review_workflow_section.py"
    ).read_text(encoding="utf-8")

    checklist_index = source.rindex("render_simple_plant_wizard_route_checklist_section(")
    package_entry_index = source.rindex("render_simple_plant_wizard_package_entry_section(")
    advanced_index = source.index('st.markdown("**Plant Review section map**")')

    assert checklist_index < package_entry_index < advanced_index
    assert 'with st.expander("查看审查包草稿预览", expanded=False):' in source
