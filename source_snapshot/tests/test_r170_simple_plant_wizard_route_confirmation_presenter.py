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

from services.plant_simple_wizard_route_confirmation_presenter import (
    build_simple_plant_wizard_route_confirmation_presenter,
)
from services.plant_simple_wizard_route_schema import HANDOFF_STAGE_ID
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


def _payload(goal: str, **options: Any) -> dict[str, Any]:
    return build_simple_plant_wizard_route_confirmation_presenter(
        options={"user_goal_text": goal, **options}
    )


def test_protein_expression_input_produces_route_1_confirmation() -> None:
    payload = _payload(
        "Express a target protein enzyme in rice seed",
        available_materials=["target_gene_or_cds", "host_plant"],
    )

    assert payload["recommended_route"]["route_id"] == "plant_protein_expression_review"
    assert payload["confidence"] in {"high", "medium"}
    assert payload["confirmation_actions"][0]["requires_user_confirmation"] is True


def test_clear_chinese_protein_goal_produces_confirmable_route_card() -> None:
    payload = _payload("我想在水稻中表达一个种子蛋白")

    assert payload["recommended_route"]["route_id"] == "plant_protein_expression_review"
    assert payload["recommended_route"]["result_label_zh"] == "蛋白表达审查"
    assert payload["confidence"] == "high"
    assert payload["decision_state"] == "ready_for_user_confirmation"
    assert payload["clarification_questions_zh"] == []
    assert payload["match_reasons_zh"] == [
        "提到了“表达”",
        "提到了“种子蛋白”",
        "提到了植物宿主“水稻”",
    ]
    assert payload["confirmation_actions"][0]["label_zh"] == "确认路线并进入资料补齐"
    assert payload["confirmation_actions"][1]["label_zh"] == "修改目标描述"


def test_artemisinin_ambiguous_input_requires_clarification() -> None:
    payload = _payload("I want to make artemisinin")

    assert payload["recommended_route"] is None
    assert payload["confidence"] in {"medium", "low"}
    assert [route["route_id"] for route in payload["alternative_routes"]] == [
        "plant_metabolic_pathway_review",
        "plant_multigene_construct_review",
    ]
    assert payload["clarification_questions_zh"] == [
        "代谢路线",
        "表达其中某个酶 / 蛋白",
        "多基因构建",
    ]


def test_multigene_construct_input_suggests_route_3() -> None:
    payload = _payload("Plan a multigene multi-cassette construct with multiple genes")

    assert payload["recommended_route"]["route_id"] == "plant_multigene_construct_review"


def test_regulatory_module_input_suggests_route_4() -> None:
    payload = _payload("Review a stress response promoter TF and cis-element reporter module")

    assert payload["recommended_route"]["route_id"] == "plant_regulatory_module_review"


def test_low_confidence_input_does_not_force_a_route() -> None:
    payload = _payload("I want to do plant engineering")

    assert payload["recommended_route"] is None
    assert payload["confidence"] == "low"
    assert payload["clarification_questions_zh"]
    assert "需要更多信息" in payload["confidence_reason_zh"]


def test_confirmation_actions_require_user_confirmation_only_for_confirm_action() -> None:
    payload = _payload("Express a target protein enzyme in tobacco leaves")

    actions = {action["action_id"]: action for action in payload["confirmation_actions"]}
    assert actions["confirm_route"]["requires_user_confirmation"] is True
    assert actions["change_route"]["requires_user_confirmation"] is False
    assert actions["confirm_route"]["label_zh"] == "确认路线并进入资料补齐"
    assert actions["change_route"]["label_zh"] == "修改目标描述"


def test_handoff_stage_remains_shared_package_review_stage() -> None:
    payload = _payload("flavonoid pathway")

    assert payload["handoff_stage_id"] == HANDOFF_STAGE_ID


def test_payload_is_deterministic() -> None:
    first = _payload(
        "multiple enzymes for alkaloid pathway",
        selected_goal_type="metabolic_pathway",
        available_materials=["target_product", "literature_evidence"],
    )
    second = _payload(
        "multiple enzymes for alkaloid pathway",
        selected_goal_type="metabolic_pathway",
        available_materials=["target_product", "literature_evidence"],
    )

    assert first == second


def test_payload_contains_only_plain_python_types() -> None:
    _walk_plain_values(_payload("promoter reporter module"))


def test_safety_text_does_not_contain_forbidden_claims() -> None:
    blob = _text_blob(_payload("promoter and pathway review")).casefold()

    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in blob


def test_ui_mount_renders_confirmation_card_without_action_buttons(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_simple_plant_wizard_route_confirmation_card()
    rendered = "\n".join(
        fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    assert payload["recommended_route"]["route_id"] == "plant_protein_expression_review"
    assert "系统判断" in rendered
    assert "bds-simple-plant-wizard-confirmation" in rendered
    assert "Confirmation actions shown as read-only labels" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_confirmation_card_mounts_after_route_cards_before_advanced_detail() -> None:
    source = (
        Path(ROOT)
        / "views"
        / "pathway_workspace_sections"
        / "plant_review_workflow_section.py"
    ).read_text(encoding="utf-8")

    route_cards_index = source.rindex("render_simple_plant_wizard_homepage_route_cards()")
    confirmation_index = source.rindex("render_simple_plant_wizard_intake_form_mock()")
    advanced_index = source.index('st.markdown("**Plant Review section map**")')

    assert route_cards_index < confirmation_index < advanced_index
    assert "_render_simple_wizard_analysis_result(" in source
