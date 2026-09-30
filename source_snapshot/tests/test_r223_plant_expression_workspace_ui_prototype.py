# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.module_registry import MODULE_REGISTRY
from services.plant_expression_workspace_prototype_presenter import (
    build_plant_expression_workspace_prototype_presenter,
)
from services.simple_plant_wizard_ui_surface_registry import (
    ADVANCED_NAVIGATION_PAGE_KEYS,
    list_ui_surfaces,
)
from views import Plant_Expression_Workspace as page


CHANGED_FILES = (
    ROOT / "app.py",
    ROOT / "core" / "module_registry.py",
    ROOT / "services" / "plant_expression_workspace_prototype_presenter.py",
    ROOT / "services" / "simple_plant_wizard_ui_surface_registry.py",
    ROOT / "views" / "Plant_Expression_Workspace.py",
    ROOT / "tests" / "test_r223_plant_expression_workspace_ui_prototype.py",
    ROOT / "docs" / "qa" / "V2_7_R223_PLANT_EXPRESSION_WORKSPACE_UI_PROTOTYPE_QA.md",
)

REMOVED_CONSTRUCT_TASK_R223_PATHS = (
    ROOT / "services" / "plant_construct_task_draft_readback.py",
    ROOT / "tests" / "test_r223_construct_task_draft_readback.py",
    ROOT / "docs" / "qa" / "V2_7_R223_CONSTRUCT_TASK_DRAFT_READBACK_QA.md",
)


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_OUTPUT_FRAGMENTS = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
)


def _minimal_chain_output() -> dict[str, Any]:
    return {
        "fixture_id": "r223_fixture",
        "chain_summary": {"route_id": "plant_expression_route_review"},
        "route_draft": {
            "draft_status": "manual_review_required",
            "intent_summary": {
                "target_or_product_terms": "rice albumin documentation record",
                "host_plant_terms": "rice",
            },
            "evidence_summary": [{"evidence_id": "placeholder-evidence", "status": "manual_review"}],
        },
        "package_snapshot": {
            "package_title": "R223 plant expression workspace prototype",
            "package_status": "manual_review_required",
            "package_scope": "documentation review",
            "construct_slot_plan_section": {
                "construct_slot_rows": [
                    {"slot_name": "promoter_slot", "value": "promoter source note"},
                    {"slot_name": "promoter_source_reference", "value": "manual source note"},
                    {"slot_name": "cds_label", "value": "albumin-like CDS label"},
                    {"slot_name": "terminator_slot", "value": ""},
                    {"slot_name": "backbone_label", "value": "vector/backbone note"},
                ]
            },
            "component_candidate_section": {
                "slot_candidate_rows": [
                    {
                        "slot_type": "promoter_slot",
                        "candidate_label": "promoter source note",
                        "review_status": "manual review pending",
                    }
                ],
                "unmatched_slot_rows": [],
            },
            "gap_queue_section": {
                "queue_items": [
                    {
                        "gap_id": "gap-terminator",
                        "field_name": "terminator_source_reference",
                        "message": "Terminator source note is missing.",
                        "source_section": "gap queue",
                    }
                ]
            },
        },
        "markdown_readback": {"markdown_text": "Documentation-only readback"},
    }


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )


def test_presenter_builds_plain_read_only_workspace_payload() -> None:
    presenter = build_plant_expression_workspace_prototype_presenter(_minimal_chain_output())

    assert presenter["page_title"] == "Plant Expression Workspace"
    assert presenter["read_only"] is True
    assert presenter["empty_state"]["is_empty"] is False
    assert presenter["workspace_summary"]["plant_host"] == "rice"
    assert presenter["workspace_summary"]["progress_percent"] > 0
    assert len(presenter["construct_components"]) == 6
    assert any(row["status"] == "Needs documentation" for row in presenter["construct_components"])
    assert presenter["gaps"]
    assert "documentation" in presenter["boundary_notice"].casefold()


def test_navigation_and_module_registry_include_prototype_as_advanced_surface() -> None:
    surfaces = {row["surface_id"]: row for row in list_ui_surfaces()}
    modules = {row["id"]: row for row in MODULE_REGISTRY}

    assert "Plant Expression Workspace" in ADVANCED_NAVIGATION_PAGE_KEYS
    assert surfaces["plant_expression_workspace"]["page_key"] == "Plant Expression Workspace"
    assert surfaces["plant_expression_workspace"]["default_visible"] is False
    assert surfaces["plant_expression_workspace"]["advanced_mode_required"] is True
    assert modules["plant_expression_workspace"]["route_key"] == "Plant Expression Workspace"


def test_page_render_example_mode_stays_read_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    presenter = build_plant_expression_workspace_prototype_presenter(_minimal_chain_output())
    fake_st.radio_values["r224_plant_expression_workspace_source_mode"] = "Example read-only demonstration"
    monkeypatch.setattr(page, "st", fake_st)
    monkeypatch.setattr(
        page,
        "build_plant_expression_workspace_prototype_presenter",
        lambda *args, **kwargs: presenter,
    )

    returned = page.render()
    rendered = _rendered_text(fake_st).casefold()

    assert returned == presenter
    assert "plant expression workspace" in rendered
    assert "expression construct overview" in rendered
    assert "current gaps and next action" in rendered
    assert "documentation-only workspace" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_old_construct_task_r223_files_are_not_part_of_official_batch() -> None:
    for path in REMOVED_CONSTRUCT_TASK_R223_PATHS:
        assert not path.exists()


def test_official_r223_copy_avoids_forbidden_claims() -> None:
    changed_text = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    payload_text = str(build_plant_expression_workspace_prototype_presenter(_minimal_chain_output()))
    lowered = f"{changed_text}\n{payload_text}".casefold()

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in lowered
    assert "documentation-only" in lowered
    assert "read-only" in lowered
