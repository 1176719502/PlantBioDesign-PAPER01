# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("vali", "dated ", "construct"),
    _term("opti", "mized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("proto", "col"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
    _term("final ", "package"),
    _term("exported ", "package"),
)


def _workflow() -> dict[str, Any]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": ["component warning: source/provenance review"],
        "adapter_input": {
            "evidence_records": [
                {"id": "EV-1", "paper_title": "Rice albumin source", "workspace_source_key": "sources"}
            ],
            "component_records": [
                {
                    "component_id": "COMP-1",
                    "component_name": "Rice albumin CDS source",
                    "component_type": "cds_source",
                    "workspace_source_key": "component_library",
                }
            ],
        },
        "chain_result": {
            "plant_review_package": {
                "package_status": "manual_review_required",
                "route_summary": {
                    "route_id": "rice_seed_protein_expression",
                    "route_label": "Rice Seed Protein Expression",
                    "route_type": "plant_expression_vector",
                },
                "construct_slot_summary": {
                    "slots": [
                        {
                            "slot_id": "cds_label",
                            "slot_label": "CDS label",
                            "required": True,
                            "evidence_ids": ["EV-1"],
                            "component_ids": ["COMP-1"],
                            "slot_status": ["candidate_evidence_manual_review"],
                            "missing_required_slot": False,
                        }
                    ]
                },
            },
            "route_draft": {"draft_status": "manual_review_required"},
        },
        "handoff_preview_payload": {
            "handoff_status": "manual_review_required",
            "missing_information_items": [
                {
                    "item_id": "gap-1",
                    "category": "evidence_gap",
                    "slot_id": "promoter_slot",
                    "reason": "Source review remains open.",
                }
            ],
        },
        "traceability": {
            "upstream_statuses": {
                "extractor": "ready_for_adapter",
                "adapter": "manual_review_required",
                "chain": "manual_review_required",
                "handoff": "manual_review_required",
            },
            "adapter_traceability": {
                "evidence_record_ids": ["EV-1"],
                "component_record_ids": ["COMP-1"],
            },
            "extractor_traceability": {
                "source_keys_used": ["project_id", "sources", "component_library"],
            },
        },
    }


def _project() -> dict[str, Any]:
    return {
        "id": 7,
        "name": "Rice albumin review workspace",
        "target_product": "rice seed albumin-like protein",
        "host": "Oryza sativa rice",
        "description": "Document a rice seed albumin-like plant expression vector review route.",
    }


def _steps() -> list[dict[str, Any]]:
    return [
        {
            "id": 10,
            "step_name": "Albumin CDS source context",
            "gene_name": "rice albumin-like CDS",
            "organism_source": "Oryza sativa rice",
            "notes": "Local source/provenance note.",
        }
    ]


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )


def test_plant_review_workflow_section_defaults_to_beginner_wizard_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    def _unexpected_build_workflow(_workspace_state: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("advanced workflow should not be built in default beginner mode")

    def _unexpected_advanced_render(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("advanced reviewer content should not render by default")

    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", _unexpected_advanced_render)
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", _unexpected_advanced_render)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", _unexpected_advanced_render)

    workflow = section.render_plant_review_workflow_section(
        project=_project(),
        steps=_steps(),
        expression_links=[],
        test_records=[{"id": "test-record-1", "test_name": "Local evidence record"}],
        review_signals=[],
        build_workflow=_unexpected_build_workflow,
    )
    rendered = _rendered_text(fake_st)

    assert workflow["workflow_status"] == "simple_plant_wizard_beginner_mode"
    assert workflow["advanced_details_visible"] is False
    assert "我们要帮你审查什么植物设计？" in rendered
    assert "用一句话描述目标，系统会先判断路线，再告诉你还缺哪些信息。" in rendered
    assert fake_st.text_area_calls[0]["label"] == "植物设计目标"
    assert "开始分析" in [call["label"] for call in fake_st.button_calls]
    assert "这个工具做什么？" in rendered
    assert "你需要准备什么？" in rendered
    assert "会得到什么？" in rendered
    assert "常见类型" not in rendered
    button_labels = [call["label"] for call in fake_st.button_calls]
    assert "蛋白表达" not in button_labels
    assert "代谢路线" not in button_labels
    assert "多基因构建" not in button_labels
    assert "调控模块" not in button_labels
    assert "Plant Review Workflow" not in rendered
    assert "Simple Plant Wizard | Beginner Mode Active | R179" not in rendered
    assert "R178" not in rendered
    assert "R179" not in rendered
    assert "plant_handoff_package_review" not in rendered
    assert section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_NOTE in rendered
    assert "bds-simple-plant-wizard-routes" not in rendered
    assert "bds-simple-plant-wizard-intake-form" not in rendered
    assert "bds-simple-plant-wizard-confirmation" not in rendered
    assert "bds-simple-plant-wizard-checklist" not in rendered
    assert "bds-simple-plant-wizard-package-entry" not in rendered
    assert [call["label"] for call in fake_st.checkbox_calls] == [section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_LABEL]
    assert fake_st.checkbox_calls[0]["value"] is False
    assert any(call["label"] == section.SIMPLE_PLANT_WIZARD_ADVANCED_EXPANDER_LABEL for call in fake_st.expander_calls)
    assert section.PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL not in [call["label"] for call in fake_st.expander_calls]
    assert section.PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL not in [call["label"] for call in fake_st.expander_calls]
    assert section.PLANT_REVIEW_READBACK_EXPANDER_LABEL not in [call["label"] for call in fake_st.expander_calls]
    assert "Route summary" not in rendered
    assert "Construct slot summary" not in rendered
    assert "Evidence summary" not in rendered
    assert "Component candidate summary" not in rendered
    assert "Gap / manual review queue" not in rendered
    assert "Package status / warnings" not in rendered
    assert "Traceability" not in rendered
    assert "Documentation-only/manual-review boundary" not in rendered
    assert "bds-review-map" not in rendered
    assert "开始分析" in button_labels
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_simple_plant_design_wizard_landing_renders_beginner_flow_without_workspace_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)

    assert workflow["workflow_status"] == "simple_plant_wizard_beginner_mode"
    assert "我们要帮你审查什么植物设计？" in rendered
    assert "植物设计目标" in fake_st.text_area_calls[0]["label"]
    assert "这个工具做什么？" in rendered
    assert "常见类型" not in rendered
    assert "Simple Plant Wizard | Beginner Mode Active | R179" not in rendered
    assert "bds-simple-plant-wizard-routes" not in rendered
    assert "bds-simple-plant-wizard-intake-form" not in rendered
    assert "bds-simple-plant-wizard-confirmation" not in rendered
    assert "bds-simple-plant-wizard-checklist" not in rendered
    assert "bds-simple-plant-wizard-package-entry" not in rendered
    assert "Pathway Workspace" not in rendered
    assert "No active pathway project selected" not in rendered
    assert "Go to Pathway Projects" not in rendered
    assert "开始分析" in [call["label"] for call in fake_st.button_calls]
    assert fake_st.download_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_single_step_analysis_shows_one_concise_route_card_for_clear_protein_goal(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_area_values[section.SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY] = (
        "我想在水稻中表达一个种子蛋白"
    )
    fake_st.button_values["r180_simple_plant_wizard_start_analysis"] = True
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)

    assert workflow["intake_state"]["confirmation_payload"]["recommended_route"]["route_id"] == (
        "plant_protein_expression_review"
    )
    assert "系统判断" in rendered
    assert "推荐路线：蛋白表达审查" in rendered
    assert "置信度：高" in rendered
    assert "判断依据" in rendered
    assert "表达" in rendered
    assert "种子蛋白" in rendered
    assert "水稻" in rendered
    assert "下一步" in rendered
    assert "请确认这个路线是否符合你的目标。" in rendered
    assert section.SIMPLE_PLANT_WIZARD_CONFIRM_ROUTE_LABEL in [call["label"] for call in fake_st.button_calls]
    assert "修改目标描述" in [call["label"] for call in fake_st.button_calls]
    assert "目标阅读" not in rendered
    assert "目标回读" not in rendered
    assert "理由 3" not in rendered
    assert "还需要确认一个问题" not in rendered
    assert "ready_for_user_confirmation" not in rendered
    assert "plant_protein_expression_review" not in rendered
    assert "route_id" not in rendered
    assert "蛋白表达" not in [call["label"] for call in fake_st.button_calls]
    assert "代谢路线" not in [call["label"] for call in fake_st.button_calls]
    assert "bds-simple-plant-wizard-checklist" not in rendered
    assert "bds-simple-plant-wizard-package-entry" not in rendered


def test_ambiguous_artemisinin_goal_asks_clarification_without_forcing_route(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.text_area_values[section.SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY] = "我想做青蒿素"
    fake_st.button_values["r180_simple_plant_wizard_start_analysis"] = True
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)

    assert workflow["intake_state"]["confirmation_payload"]["recommended_route"] is None
    assert "还需要确认一个" in rendered
    assert "你想从哪个角度整理青蒿素相关设计？" in rendered
    assert section.SIMPLE_PLANT_WIZARD_CONFIRM_ROUTE_LABEL not in [call["label"] for call in fake_st.button_calls]
    clarification_buttons = [
        call["label"]
        for call in fake_st.button_calls
        if call["key"] and str(call["key"]).startswith("r180_simple_plant_wizard_clarify_")
    ]
    assert clarification_buttons == ["代谢路线", "表达其中某个酶 / 蛋白", "多基因构建"]
    assert "bds-simple-plant-wizard-checklist" not in rendered
    assert "bds-simple-plant-wizard-package-entry" not in rendered


def test_empty_goal_clears_stale_analysis_state_and_keeps_default_clean(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ANALYZED_KEY] = True
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY] = (
        "我想在水稻中表达一个种子蛋白"
    )
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_CONFIRMED_KEY] = True
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY] = "plant_protein_expression_review"
    monkeypatch.setattr(section, "st", fake_st)

    workflow = section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)

    assert workflow["intake_state"]["confirmed"] is False
    assert fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ANALYZED_KEY] is False
    assert section.SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY not in fake_st.session_state
    assert section.SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY not in fake_st.session_state
    assert "我们要帮你审查什么植物设计？" in rendered
    assert "这个工具做什么？" in rendered
    assert "还需要确认一个问题" not in rendered
    assert "推荐路线" not in rendered
    assert "系统判断" not in rendered
    assert "plant_handoff_package_review" not in rendered


def test_confirmed_route_shows_checklist_and_package_only_in_collapsed_sections(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ANALYZED_KEY] = True
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY] = (
        "Express a target protein enzyme in rice seed"
    )
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_CONFIRMED_KEY] = True
    fake_st.session_state[section.SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY] = "plant_protein_expression_review"
    fake_st.text_area_values[section.SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY] = (
        "Express a target protein enzyme in rice seed"
    )
    monkeypatch.setattr(section, "st", fake_st)

    section.render_simple_plant_design_wizard_landing()
    rendered = _rendered_text(fake_st)
    expander_states = {call["label"]: call.get("expanded") for call in fake_st.expander_calls}

    assert expander_states["查看需要补充的信息"] is False
    assert expander_states["查看审查包草稿预览"] is False
    assert "bds-simple-plant-wizard-checklist" in rendered
    assert "bds-simple-plant-wizard-package-entry" in rendered
    assert "Current project draft / 当前项目草稿" in rendered
    assert section.SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY in fake_st.session_state


def test_plant_review_workflow_section_renders_advanced_sections_when_enabled(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)

    captured_state: dict[str, Any] = {}
    advanced_calls = {"package": 0, "handoff": 0, "seed": 0}

    def _build_workflow(workspace_state: dict[str, Any]) -> dict[str, Any]:
        captured_state.update(workspace_state)
        return _workflow()

    def _render_package() -> dict[str, Any]:
        advanced_calls["package"] += 1
        return {}

    def _render_handoff(_payload: dict[str, Any]) -> None:
        advanced_calls["handoff"] += 1
        fake_st.markdown("advanced handoff rendered")

    def _render_seed() -> None:
        advanced_calls["seed"] += 1
        fake_st.markdown("advanced seed review rendered")

    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", _render_package)
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", _render_handoff)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", _render_seed)

    workflow = section.render_plant_review_workflow_section(
        project=_project(),
        steps=_steps(),
        expression_links=[],
        test_records=[{"id": "test-record-1", "test_name": "Local evidence record"}],
        review_signals=[],
        build_workflow=_build_workflow,
    )
    rendered = _rendered_text(fake_st)

    assert workflow["workflow_status"] == "manual_review_required"
    assert workflow["advanced_details_visible"] is True
    assert captured_state["project_id"] == "7"
    assert captured_state["component_records"][0]["component_name"] == "rice albumin-like CDS"
    assert captured_state["evidence_records"][0]["paper_title"] == "Local evidence record"
    assert "Route summary" in rendered
    assert "Construct slot summary" in rendered
    assert "Evidence summary" in rendered
    assert "Component candidate summary" in rendered
    assert "Gap / manual review queue" in rendered
    assert "Package status / warnings" in rendered
    assert "Traceability" in rendered
    assert "Documentation-only/manual-review boundary" in rendered
    assert "bds-review-map" in rendered
    top_level_expanders = {
        call["label"]: call.get("expanded")
        for call in fake_st.expander_calls
        if call["label"]
        in {
            section.PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL,
            section.PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL,
            section.PLANT_REVIEW_READBACK_EXPANDER_LABEL,
        }
    }
    assert top_level_expanders == {
        section.PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL: False,
        section.PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL: False,
        section.PLANT_REVIEW_READBACK_EXPANDER_LABEL: False,
    }
    assert any(call["label"] == "Full Construct slot summary table" for call in fake_st.expander_calls)
    assert any(call["label"] == "Full Traceability table" for call in fake_st.expander_calls)
    assert advanced_calls == {"package": 1, "handoff": 1, "seed": 1}


def test_pathway_workspace_mounts_plant_review_tab_and_section() -> None:
    workspace_source = (ROOT / "views" / "PathwayWorkspace.py").read_text(encoding="utf-8")

    assert "render_plant_review_workflow_section" in workspace_source
    assert '"Plant Review"' in workspace_source
    assert "with plant_review_tab:" in workspace_source


def test_simple_plant_wizard_default_mounts_single_step_before_collapsed_later_sections() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py").read_text(
        encoding="utf-8"
    )

    route_cards_index = source.index("render_simple_plant_wizard_homepage_route_cards()")
    intake_index = source.index("render_simple_plant_wizard_intake_form_mock()")
    checklist_index = source.rindex("render_simple_plant_wizard_route_checklist_section(")
    package_entry_index = source.rindex("render_simple_plant_wizard_package_entry_section(")
    advanced_index = source.index("with st.expander(PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL")
    proof_path_index = source.index("with st.expander(PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL")
    readback_index = source.index("with st.expander(PLANT_REVIEW_READBACK_EXPANDER_LABEL")

    assert route_cards_index < intake_index < checklist_index < package_entry_index < advanced_index
    assert 'with st.expander("查看需要补充的信息", expanded=False):' in source
    assert 'with st.expander("查看审查包草稿预览", expanded=False):' in source
    assert package_entry_index < advanced_index < proof_path_index < readback_index


def test_existing_advanced_review_functions_remain_reachable_behind_advanced_mode_gate() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py").read_text(
        encoding="utf-8"
    )

    assert "show_advanced_details = _should_show_simple_plant_wizard_advanced_details(st)" in source
    assert "if not show_advanced_details:" in source
    assert "with st.expander(SIMPLE_PLANT_WIZARD_ADVANCED_EXPANDER_LABEL, expanded=False):" in source
    assert "with st.expander(PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL, expanded=False):" in source
    assert "with st.expander(PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL, expanded=False):" in source
    assert "with st.expander(PLANT_REVIEW_READBACK_EXPANDER_LABEL, expanded=False):" in source
    assert "render_plant_goal_review_package_draft_visible_mvp()" in source
    assert "render_plant_review_handoff_preview_section" in source
    assert "render_rice_albumin_seed_review_visible_mount()" in source


def test_plant_review_workflow_section_copy_keeps_safety_boundary() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py").read_text(
        encoding="utf-8"
    )
    test_source = (ROOT / "tests" / "test_plant_review_workflow_workspace_mount.py").read_text(encoding="utf-8")
    text = f"{source}\n{test_source}".casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text
    assert "documentation-only" in text
    assert "read-only" in text
