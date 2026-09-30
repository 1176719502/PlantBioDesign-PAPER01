# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "plant_seed" / "rice_albumin"
SEED_FILES = (
    SEED_DIR / "route_contexts.json",
    SEED_DIR / "component_records.json",
    SEED_DIR / "evidence_records.json",
)


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
    _term("best ", "component"),
    _term("recommended ", "component"),
    _term("accepted", "-", "evidence"),
)


def _rendered_text(fake_st: FakeStreamlit) -> str:
    parts: list[str] = []
    parts.extend(fake_st.subheaders)
    parts.extend(fake_st.caption_messages)
    parts.extend(fake_st.info_messages)
    parts.extend(str(call["body"]) for call in fake_st.markdown_calls)
    parts.extend(frame.to_string(index=False) for frame in fake_st.dataframes)
    parts.extend(f"{call['label']}: {call['value']}" for call in fake_st.metric_calls)
    return "\n".join(parts)


def test_r165_visible_mvp_renders_r163_rice_albumin_package_counts(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    before = {path.name: path.read_bytes() for path in SEED_FILES}

    package = section.render_plant_goal_review_package_draft_visible_mvp()
    rendered = _rendered_text(fake_st)
    after = {path.name: path.read_bytes() for path in SEED_FILES}

    assert package["package_status"] == "design_review_package_draft_ready"
    assert package["dataset_key"] == "rice_albumin"
    assert package["fail_closed"] is False
    assert package["matched_seed_records"]["represented_seed_record_count"] == 12
    assert package["manual_review_task_summary"]["manual_provenance_queue_task_count"] == 46
    assert package["manual_review_task_summary"]["records_blocked_from_promotion"] == 12
    assert package["promotion_boundary"]["ready_to_promote_count"] == 0
    assert package["promotion_boundary"]["promotion_allowed_count"] == 0
    assert package["construct_status_summary"]["construct_task"]["auto_created"] is False
    assert package["construct_status_summary"]["construct_draft"]["auto_created"] is False
    assert package["provenance_gap_summary"]["identifier_autofill"]["performed"] is False
    assert package["promotion_boundary"]["record_was_promoted"] is False
    assert before == after

    assert "Plant Goal -> Design Review Package Draft" in rendered
    assert "Review a rice albumin-like protein expression design in a plant system." in rendered
    assert "Design Intent" in rendered
    assert "Required design slots" in rendered
    assert "Matched seed records" in rendered
    assert "Evidence/provenance gaps" in rendered
    assert "Candidate route and construct status" in rendered
    assert "Construct task" in rendered
    assert "Construct draft" in rendered
    assert "Manual review tasks" in rendered
    assert "Promotion boundary" in rendered
    assert "Next human actions" in rendered
    assert "Blocked outputs / safety boundary" in rendered
    assert "Seed records represented" in rendered
    assert "12" in rendered
    assert "46" in rendered
    assert "Ready-to-promote count" in rendered
    assert "Promotion-allowed count" in rendered
    assert "unavailable manual review required" in rendered
    assert "no source or database identifier is filled" in rendered
    assert any(call["label"] == "Plant goal review package draft goal" for call in fake_st.selectbox_calls)
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_r165_visible_mvp_uses_injected_r163_service_output(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    calls: list[tuple[Any, str | None]] = []

    def _fake_build_package(goal_text: Any, dataset_key: str | None) -> dict[str, Any]:
        calls.append((goal_text, dataset_key))
        return {
            "package_status": "synthetic_test_package_status",
            "goal_text": str(goal_text),
            "dataset_key": dataset_key or "rice_albumin",
            "fail_closed": False,
            "intent_summary": {
                "section_title": "Design Intent",
                "intent_status": "synthetic_intent_status",
                "summary": "Synthetic service output marker.",
            },
            "matched_seed_records": {"represented_seed_record_count": 2, "records": []},
            "manual_review_task_summary": {
                "manual_provenance_queue_task_count": 3,
                "represented_record_count": 2,
                "records_blocked_from_promotion": 2,
                "ready_to_promote_count": 0,
                "promotion_allowed_count": 0,
                "manual_review_required": True,
            },
            "promotion_boundary": {
                "ready_to_promote_count": 0,
                "promotion_allowed_count": 0,
                "boundary_note": "Synthetic promotion boundary.",
            },
            "construct_status_summary": {
                "construct_task": {"status": "unavailable_manual_review_required", "auto_created": False},
                "construct_draft": {"status": "unavailable_manual_review_required", "auto_created": False},
            },
            "candidate_route_summary": {"candidate_route_status": "manual_review_required", "dataset_key": dataset_key},
            "evidence_summary": {},
            "provenance_gap_summary": {"identifier_autofill": {"performed": False}},
            "design_slots": [],
            "next_human_actions": [],
            "blocked_outputs": [],
            "documentation_boundary": "Synthetic documentation-only boundary.",
        }

    package = section.render_plant_goal_review_package_draft_visible_mvp(build_package=_fake_build_package)
    rendered = _rendered_text(fake_st)

    assert calls == [(section.DEFAULT_PLANT_GOAL_REVIEW_PACKAGE_GOAL, "rice_albumin")]
    assert package["package_status"] == "synthetic_test_package_status"
    assert "Synthetic service output marker." in rendered
    assert "synthetic test package status" in rendered
    assert "2" in rendered
    assert "3" in rendered


def test_r165_visible_mvp_fails_closed_for_non_plant_selection(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.selectbox_values["r165_plant_goal_review_package_goal_choice"] = "Unsupported non-plant example"
    monkeypatch.setattr(section, "st", fake_st)

    package = section.render_plant_goal_review_package_draft_visible_mvp()
    rendered = _rendered_text(fake_st)

    assert package["fail_closed"] is True
    assert package["package_status"] == "design_review_package_draft_fail_closed"
    assert package["matched_seed_records"]["represented_seed_record_count"] == 0
    assert package["manual_review_task_summary"]["ready_to_promote_count"] == 0
    assert package["manual_review_task_summary"]["promotion_allowed_count"] == 0
    assert package["construct_status_summary"]["construct_task"]["auto_created"] is False
    assert package["construct_status_summary"]["construct_draft"]["auto_created"] is False
    assert package["promotion_boundary"]["record_was_promoted"] is False
    assert "outside the plant-only R163 MVP scope" in rendered
    assert "Use a rice albumin-like plant goal with dataset_key rice_albumin." in rendered
    assert "design review package draft fail closed" in rendered


def test_r165_visible_mvp_keeps_artemisia_inactive(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.selectbox_values["r165_plant_goal_review_package_goal_choice"] = "Unsupported plant dataset example"
    monkeypatch.setattr(section, "st", fake_st)

    package = section.render_plant_goal_review_package_draft_visible_mvp()
    rendered = _rendered_text(fake_st)
    artemisia = package["candidate_route_summary"]["artemisia_annua_status"]

    assert package["fail_closed"] is True
    assert package["dataset_key"] == "artemisia_annua"
    assert artemisia["active_dataset_profile"] is False
    assert artemisia["conversion_allowed"] is False
    assert artemisia["included_in_mvp_path"] is False
    assert "Artemisia annua" in rendered
    assert "inactive in the R165 visible MVP path" in rendered


def test_r165_visible_mvp_changed_sources_avoid_forbidden_claim_wording() -> None:
    source_text = "\n".join(
        [
            (ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py").read_text(
                encoding="utf-8"
            ),
            (ROOT / "tests" / "test_r165_plant_goal_review_package_visible_mvp.py").read_text(encoding="utf-8"),
        ]
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in source_text
    assert "documentation-only" in source_text
    assert "manual review" in source_text
