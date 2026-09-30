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


def test_each_entry_route_returns_non_empty_slot_checklist() -> None:
    for route_id in ENTRY_ROUTE_IDS:
        payload = build_simple_plant_wizard_route_checklist_presenter(route_id)

        assert payload["route_id"] == route_id
        assert payload["slot_rows"]
        assert payload["completion_summary"]["total_slots"] == len(payload["slot_rows"])


def test_handoff_stage_id_is_shared_package_review_stage() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter("plant_protein_expression_review")

    assert payload["handoff_stage_id"] == HANDOFF_STAGE_ID


def test_unknown_route_returns_safe_empty_payload_without_exception() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter("unknown_route")

    assert payload["route_id"] == "unknown_route"
    assert payload["route_label_en"] == "Unknown route"
    assert payload["slot_rows"] == []
    assert payload["completion_summary"]["total_slots"] == 0
    assert payload["next_step_actions"] == []


def test_default_slot_records_produce_missing_incomplete_state() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter("plant_protein_expression_review")
    summary = payload["completion_summary"]

    assert summary["filled_slots"] == 0
    assert summary["missing_slots"] > 0
    assert summary["completion_label_zh"] == "信息不完整"
    assert any(row["status"] == "missing" for row in payload["slot_rows"])


def test_provided_filled_slot_records_update_completion_counts() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter(
        "plant_protein_expression_review",
        slot_records=[
            {"slot_id": "target_protein", "value": "albumin-like protein", "has_provenance": True},
            {"slot_id": "gene_or_cds", "status": "filled", "evidence_status": "recorded"},
        ],
    )

    assert payload["completion_summary"]["filled_slots"] == 2
    statuses = {row["slot_id"]: row["status"] for row in payload["slot_rows"]}
    assert statuses["target_protein"] == "filled"
    assert statuses["gene_or_cds"] == "filled"


def test_missing_provenance_is_counted_separately_from_missing_fields() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter(
        "plant_protein_expression_review",
        slot_records=[
            {"slot_id": "promoter", "status": "missing_provenance"},
        ],
    )

    assert payload["completion_summary"]["missing_provenance_slots"] >= 1
    assert "promoter" in payload["gap_summary"]["missing_evidence_or_provenance"]["slot_ids"]
    assert "promoter" not in payload["gap_summary"]["missing_core_information"]["slot_ids"]


def test_manual_review_items_are_counted_separately() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter(
        "plant_metabolic_pathway_review",
        slot_records=[
            {"slot_id": "pathway_step", "status": "needs_manual_review"},
        ],
    )

    assert payload["completion_summary"]["manual_review_slots"] >= 1
    assert "pathway_step" in payload["gap_summary"]["needs_manual_review"]["slot_ids"]


def test_next_step_actions_are_mock_read_only_and_do_not_write_data() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter("plant_regulatory_module_review")

    assert payload["next_step_actions"]
    for action in payload["next_step_actions"]:
        assert action["is_mock"] is True
        assert action["does_not_write_data"] is True
        assert action["action_kind"].startswith("mock_")


def test_completion_labels_use_safe_draft_incomplete_manual_review_wording() -> None:
    payload = build_simple_plant_wizard_route_checklist_presenter(
        "plant_multigene_construct_review",
        slot_records={"manual_review_status": {"status": "needs_manual_review"}},
    )
    labels = _text_blob(payload["completion_summary"])

    assert any(term in labels for term in ["草稿", "信息不完整", "需要人工复核", "可继续补充"])
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in labels.casefold()


def test_payload_is_deterministic_across_repeated_calls() -> None:
    first = build_simple_plant_wizard_route_checklist_presenter(
        "plant_protein_expression_review",
        slot_records=[{"slot_id": "host_plant", "value": "rice"}],
    )
    second = build_simple_plant_wizard_route_checklist_presenter(
        "plant_protein_expression_review",
        slot_records=[{"slot_id": "host_plant", "value": "rice"}],
    )

    assert first == second


def test_payload_contains_only_plain_python_types() -> None:
    _walk_plain_values(build_simple_plant_wizard_route_checklist_presenter("plant_regulatory_module_review"))


def test_safety_copy_and_generated_text_do_not_contain_forbidden_claims() -> None:
    blob = _text_blob(
        [
            build_simple_plant_wizard_route_checklist_presenter(route_id)
            for route_id in ENTRY_ROUTE_IDS
        ]
    ).casefold()

    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in blob


def test_ui_mount_renders_checklist_without_action_buttons(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_simple_plant_wizard_route_checklist_section()
    rendered = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    assert payload["route_id"] == "plant_protein_expression_review"
    assert "bds-simple-plant-wizard-checklist" in rendered
    assert "Simple route checklist" in rendered
    assert "Simple next-step mock actions" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_checklist_mounts_after_confirmation_inside_collapsed_section_before_advanced_detail() -> None:
    source = (
        Path(ROOT)
        / "views"
        / "pathway_workspace_sections"
        / "plant_review_workflow_section.py"
    ).read_text(encoding="utf-8")

    confirmation_index = source.index("_render_simple_wizard_analysis_result(")
    checklist_index = source.rindex("render_simple_plant_wizard_route_checklist_section(")
    advanced_index = source.index('st.markdown("**Plant Review section map**")')

    assert confirmation_index < checklist_index < advanced_index
    assert 'with st.expander("查看需要补充的信息", expanded=False):' in source
