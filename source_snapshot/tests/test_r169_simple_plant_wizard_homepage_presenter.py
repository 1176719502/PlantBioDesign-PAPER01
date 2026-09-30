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

from services.plant_simple_wizard_homepage_presenter import (
    build_simple_plant_wizard_homepage_presenter,
)
from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_entry_routes,
)
from views.pathway_workspace_sections import plant_review_workflow_section as section


ENTRY_ROUTE_IDS = [
    "plant_protein_expression_review",
    "plant_metabolic_pathway_review",
    "plant_multigene_construct_review",
    "plant_regulatory_module_review",
]

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


def test_homepage_presenter_returns_exactly_four_entry_route_cards() -> None:
    payload = build_simple_plant_wizard_homepage_presenter()

    assert [card["route_id"] for card in payload["route_cards"]] == ENTRY_ROUTE_IDS
    assert len(payload["route_cards"]) == 4


def test_handoff_package_stage_is_present_but_not_a_route_card() -> None:
    payload = build_simple_plant_wizard_homepage_presenter()
    card_route_ids = [card["route_id"] for card in payload["route_cards"]]

    assert payload["shared_handoff_stage"]["route_id"] == HANDOFF_STAGE_ID
    assert payload["handoff_stage_id"] == HANDOFF_STAGE_ID
    assert HANDOFF_STAGE_ID not in card_route_ids


def test_route_cards_use_r167_route_ids_labels_examples_and_handoff_stage() -> None:
    payload = build_simple_plant_wizard_homepage_presenter()
    schema_routes = {route["route_id"]: route for route in get_simple_plant_wizard_entry_routes()}

    for card in payload["route_cards"]:
        schema_route = schema_routes[card["route_id"]]
        assert card["label_zh"] == schema_route["label_zh"]
        assert card["label_en"] == schema_route["label_en"]
        assert card["button_label_zh"] == schema_route["button_label_zh"]
        assert card["short_description_zh"] == schema_route["short_description_zh"]
        assert card["examples_zh"] == schema_route["examples_zh"]
        assert card["primary_user_goal_zh"] == schema_route["primary_user_goal_zh"]
        assert card["required_slot_count"] == len(schema_route["required_slots"])
        assert card["handoff_stage_id"] == HANDOFF_STAGE_ID


def test_every_route_card_has_beginner_button_text_examples_and_confirmation_flag() -> None:
    payload = build_simple_plant_wizard_homepage_presenter()

    for card in payload["route_cards"]:
        assert card["button_label_zh"]
        assert card["examples_zh"]
        assert all(str(example).strip() for example in card["examples_zh"])
        assert card["requires_user_confirmation"] is True


def test_homepage_exposes_compact_quick_select_options_without_unsure_action() -> None:
    payload = build_simple_plant_wizard_homepage_presenter()

    assert "unsure_action" not in payload
    assert [option["label_zh"] for option in payload["quick_select_options"]] == [
        "蛋白表达",
        "代谢路线",
        "多基因构建",
        "调控模块",
    ]


def test_payload_is_deterministic_and_mutation_safe_across_calls() -> None:
    first = build_simple_plant_wizard_homepage_presenter()
    second = build_simple_plant_wizard_homepage_presenter()

    assert first == second
    first["route_cards"][0]["examples_zh"].append("mutated")
    assert build_simple_plant_wizard_homepage_presenter() == second


def test_returned_data_is_plain_values_only() -> None:
    _walk_plain_values(build_simple_plant_wizard_homepage_presenter())


def test_safety_copy_does_not_contain_forbidden_claims() -> None:
    blob = _text_blob(build_simple_plant_wizard_homepage_presenter()).casefold()

    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in blob


def test_ui_mount_renders_compact_beginner_homepage_without_route_cards(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_simple_plant_wizard_homepage_route_cards()
    rendered = "\n".join(
        fake_st.titles
        + fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    assert len(payload["route_cards"]) == 4
    assert "我们要帮你审查什么植物设计？" in rendered
    assert "用一句话描述目标，系统会先判断路线，再告诉你还缺哪些信息。" in rendered
    assert "蛋白表达" not in rendered
    assert "代谢路线" not in rendered
    assert "多基因构建" not in rendered
    assert "调控模块" not in rendered
    assert "bds-simple-plant-wizard-routes" not in rendered
    assert "我不确定，让系统帮我判断" not in rendered
    assert HANDOFF_STAGE_ID not in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_plant_review_workflow_section_mounts_simple_wizard_before_advanced_detail() -> None:
    source = (
        Path(ROOT)
        / "views"
        / "pathway_workspace_sections"
        / "plant_review_workflow_section.py"
    ).read_text(encoding="utf-8")

    simple_mount_index = source.index("render_simple_plant_wizard_homepage_route_cards()")
    workflow_status_index = source.index('st.markdown("**Plant Review section map**")')

    assert "build_simple_plant_wizard_homepage_presenter" in source
    assert simple_mount_index < workflow_status_index
