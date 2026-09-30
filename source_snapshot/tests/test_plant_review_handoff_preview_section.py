# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_handoff_preview_section as section


ROOT = Path(__file__).resolve().parents[1]


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
)


def _handoff_payload() -> dict:
    return {
        "handoff_status": "manual_review_required",
        "manual_review_required": True,
        "reviewer_summary": {
            "chain_status": "manual_review_required",
            "status_label": "manual_review_required",
            "manual_review_required": True,
            "blocked": False,
            "review_item_count": 2,
            "review_item_categories": {"evidence_gap": 1, "component_gap": 1},
            "safe_boundary_note": "Documentation-only review context.",
        },
        "required_review_items": [
            {
                "item_id": "review-1",
                "category": "evidence_gap",
                "title": "Evidence source review",
                "severity": "review_required",
                "slot_id": "promoter_slot",
                "reason": "Source context needs manual review.",
                "evidence_ids": ["EV-1"],
                "component_ids": ["COMP-1"],
            }
        ],
        "missing_information_items": [
            {
                "item_id": "missing-1",
                "category": "component_gap",
                "title": "Component provenance review",
                "severity": "review_required",
                "slot_id": "cds_label",
                "reason": "Component provenance remains open.",
            }
        ],
        "evidence_traceability_items": [{"evidence_id": "EV-1", "traceability_source": "readback_traceability"}],
        "component_traceability_items": [{"component_id": "COMP-1", "traceability_source": "readback_traceability"}],
        "blocked_output_boundaries": ["sequence_generation", "downstream_use_judgment"],
        "evidence_worksheet_handoff_readback": {
            "readback_batch": "v2.7-r125",
            "read_only": True,
            "reuse_source": "plant_evidence_review_worksheet_presenter",
            "worksheet_schema_version": "plant_evidence_review_worksheet.v2.7.r118",
            "worksheet_status": "plant_evidence_review_worksheet",
            "summary": {
                "overall_review_state": "requires manual review",
                "total_evidence_rows": 1,
                "linked_component_slot_count": 1,
                "missing_source_or_provenance_count": 1,
                "weak_or_unreviewed_evidence_count": 1,
                "manual_review_required_count": 3,
                "blocked_boundary_category_count": 2,
                "followup_queue_count": 2,
                "followup_queue_type_counts": {
                    "missing_provenance": 1,
                    "weak_or_unreviewed_evidence": 1,
                },
                "empty_input": False,
            },
            "followup_queue_status": {
                "filter_key": "followup_type",
                "selected_followup_type": "all_followup_types",
                "followup_type_options": ["missing_provenance", "weak_or_unreviewed_evidence"],
                "total_count": 2,
                "filtered_count": 2,
                "group_by_type": True,
                "group_counts": {
                    "missing_provenance": 1,
                    "weak_or_unreviewed_evidence": 1,
                },
                "empty_state": "",
                "boundary_note": "Read-only documentation-review inspection only.",
            },
            "blocked_output_boundary_categories": ["protocol", "yield_prediction"],
            "boundary_note": (
                "Evidence worksheet handoff readback is documentation-only review context for gaps and "
                "manual-review needs."
            ),
            "warnings": [],
        },
        "route_construct_traceability_readback": {
            "traceability_schema_version": "plant_route_construct_traceability_readback.v2.7.r128",
            "traceability_batch": "v2.7-r128",
            "traceability_status": "route_construct_traceability_readback",
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "reuse_source": "plant_evidence_review_worksheet_presenter",
            "summary": {
                "trace_row_count": 1,
                "evidence_link_count": 1,
                "component_slot_link_count": 1,
                "construct_slot_link_count": 1,
                "construct_slot_count": 1,
                "gap_or_followup_count": 1,
                "manual_review_required": True,
                "empty_input": False,
            },
            "intent_section": {
                "columns": ["field", "value"],
                "rows": [
                    {"field": "intent_summary", "value": "rice seed albumin-like protein; Oryza sativa rice; seed"},
                    {"field": "route_or_context_id", "value": "rice_seed_protein_expression"},
                ],
            },
            "route_context_section": {
                "columns": ["field", "value"],
                "rows": [{"field": "route_id", "value": "rice_seed_protein_expression"}],
            },
            "construct_slot_section": {
                "columns": [
                    "slot_name",
                    "display_label",
                    "status",
                    "safe_status_text",
                    "evidence_ids",
                    "source_ids",
                    "missing_reason",
                    "manual_review_required",
                ],
                "rows": [
                    {
                        "slot_name": "promoter",
                        "display_label": "Promoter",
                        "status": "needs_confirmation",
                        "safe_status_text": "needs confirmation; manual review required",
                        "evidence_ids": ["EV-1"],
                        "source_ids": ["EV-1"],
                        "missing_reason": "",
                        "manual_review_required": True,
                    }
                ],
            },
            "handoff_review_section": {
                "columns": [
                    "item_id",
                    "category",
                    "severity",
                    "linked_evidence_ids",
                    "linked_component_ids",
                    "linked_slot_id",
                    "reason",
                    "manual_review_note",
                ],
                "rows": [
                    {
                        "item_id": "manual-1",
                        "category": "provenance_gap",
                        "severity": "review_required",
                        "linked_evidence_ids": ["EV-1"],
                        "linked_component_ids": ["COMP-1"],
                        "linked_slot_id": "promoter_slot",
                        "reason": "missing_provenance_or_source",
                        "manual_review_note": "Confirm source trail before interpretation.",
                    }
                ],
            },
            "traceability_section": {
                "columns": [
                    "trace_id",
                    "route_or_context_id",
                    "intent_summary",
                    "linked_evidence_id",
                    "linked_component",
                    "linked_component_slot",
                    "linked_construct_slot",
                    "source_or_provenance_status",
                    "review_status",
                    "gap_or_followup_reason",
                    "manual_review_note",
                ],
                "rows": [
                    {
                        "trace_id": "r128-trace-001-rice_seed_protein_expression-promoter-ev-1",
                        "route_or_context_id": "rice_seed_protein_expression",
                        "intent_summary": "rice seed albumin-like protein; Oryza sativa rice; seed",
                        "linked_evidence_id": "EV-1",
                        "linked_component": "COMP-1 | Rice seed promoter component record",
                        "linked_component_slot": "promoter_slot | Promoter and leader",
                        "linked_construct_slot": "promoter",
                        "source_or_provenance_status": "source/provenance gap",
                        "review_status": "manual_review_required",
                        "gap_or_followup_reason": "missing_provenance_or_source",
                        "manual_review_note": "Confirm source trail before interpretation.",
                    }
                ],
            },
            "boundary_section": {
                "boundary_note": "Read-only plant traceability readback for documentation-only manual review.",
                "allowed_output_categories": [
                    "documentation_readback",
                    "traceability_relationships",
                    "gap_review_status",
                    "manual_review_status",
                ],
            },
            "readback_context": {
                "mount_batch": "v2.7-r129",
                "mount_surface": "plant_review_handoff_preview",
            },
            "warnings": [],
        },
        "plant_evidence_review_worksheet": {
            "worksheet_status": "plant_evidence_review_worksheet",
            "read_only": True,
            "manual_review_required": True,
            "documentation_only_boundary": "Documentation-only worksheet boundary for manual review.",
            "summary": {
                "total_evidence_rows": 1,
                "linked_component_slot_count": 1,
                "missing_source_or_provenance_count": 1,
                "weak_or_unreviewed_evidence_count": 1,
                "manual_review_required_count": 3,
                "blocked_boundary_category_count": 2,
                "followup_queue_count": 1,
                "overall_review_state": "requires manual review",
                "evidence_row_count": 1,
                "component_slot_row_count": 1,
                "manual_review_item_count": 1,
                "provenance_gap_count": 1,
                "empty_input": False,
            },
            "route_context_section": {
                "columns": ["field", "value"],
                "rows": [{"field": "route_id", "value": "rice_seed_protein_expression"}],
            },
            "evidence_review_section": {
                "columns": [
                    "row_id",
                    "evidence_item_id",
                    "evidence_label",
                    "linked_component_id",
                    "linked_slot_id",
                    "review_status",
                    "gap_reason",
                ],
                "rows": [
                    {
                        "row_id": "r118-evidence-001-promoter-slot",
                        "evidence_item_id": "EV-1",
                        "evidence_label": "Rice promoter evidence note",
                        "linked_component_id": "COMP-1",
                        "linked_slot_id": "promoter_slot",
                        "review_status": "manual_review_required",
                        "gap_reason": "missing_provenance_or_source",
                    }
                ],
            },
            "component_slot_linkage_section": {
                "columns": ["row_id", "linked_slot_id", "linked_component_id", "linked_evidence_ids", "gap_reason"],
                "rows": [
                    {
                        "row_id": "r118-component-slot-001-promoter-slot",
                        "linked_slot_id": "promoter_slot",
                        "linked_component_id": "COMP-1",
                        "linked_evidence_ids": ["EV-1"],
                        "gap_reason": "missing_provenance_or_source",
                    }
                ],
            },
            "manual_review_section": {
                "columns": ["row_id", "item_id", "category", "severity", "gap_reason"],
                "rows": [
                    {
                        "row_id": "r118-manual-review-001-provenance-gap",
                        "item_id": "manual-1",
                        "category": "provenance_gap",
                        "severity": "review_required",
                        "gap_reason": "missing_provenance_or_source",
                    }
                ],
            },
            "followup_queue_section": {
                "columns": [
                    "followup_id",
                    "followup_type",
                    "linked_evidence_id",
                    "linked_component",
                    "linked_slot",
                    "reason",
                    "suggested_review_action",
                    "review_status",
                ],
                "rows": [
                    {
                        "followup_id": "r122-followup-001-missing-provenance-promoter-slot-ev-1",
                        "followup_type": "missing_provenance",
                        "linked_evidence_id": "EV-1",
                        "linked_component": "COMP-1",
                        "linked_slot": "promoter_slot",
                        "reason": "missing_provenance_or_source",
                        "suggested_review_action": "add or confirm source/provenance documentation",
                        "review_status": "manual_review_required",
                    },
                    {
                        "followup_id": "r122-followup-002-weak-or-unreviewed-evidence-promoter-slot-ev-2",
                        "followup_type": "weak_or_unreviewed_evidence",
                        "linked_evidence_id": "EV-2",
                        "linked_component": "COMP-2",
                        "linked_slot": "promoter_slot",
                        "reason": "weak_evidence_placeholder",
                        "suggested_review_action": "confirm evidence level and review status",
                        "review_status": "unreviewed",
                    }
                ],
            },
            "boundary_section": {
                "blocked_output_categories": ["protocol", "yield_prediction"],
            },
            "warnings": [],
        },
        "source_traceability": {
            "source_kind": "chain_result",
            "source_schema_version": "plant_review_workflow_chain.v2.7.r76",
            "route_traceability_items": [{"route_id": "rice_seed_protein_expression"}],
            "handoff_context": {"surface": "workspace"},
        },
    }


def test_handoff_preview_section_renders_required_read_only_surfaces(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    section.render_plant_review_handoff_preview_section(_handoff_payload())
    rendered = "\n".join(
        fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )

    assert "Handoff preview" in rendered
    assert "Reviewer summary" in rendered
    assert "Required review items" in rendered
    assert "Missing information items" in rendered
    assert "Evidence traceability" in rendered
    assert "Component traceability" in rendered
    assert "Blocked output boundaries" in rendered
    assert "Evidence worksheet handoff readback" in rendered
    assert "Route-to-construct traceability readback" in rendered
    assert "Route-to-construct summary" in rendered
    assert "Route-to-construct intent" in rendered
    assert "Route/context readback" in rendered
    assert "Route-to-construct links" in rendered
    assert "Construct draft slots" in rendered
    assert "Handoff review links" in rendered
    assert "Route-to-construct boundary categories" in rendered
    assert "r128-trace-001-rice_seed_protein_expression-promoter-ev-1" in rendered
    assert "promoter_slot | Promoter and leader" in rendered
    assert "COMP-1 | Rice seed promoter component record" in rendered
    assert "Follow-up queue items" in rendered
    assert "R124 filter/group metadata" in rendered
    assert "Plant evidence review worksheet" in rendered
    assert "Worksheet summary rollup" in rendered
    assert "Overall review state" in rendered
    assert "requires manual review" in rendered
    assert "Missing source/provenance" in rendered
    assert "Worksheet evidence rows" in rendered
    assert "Worksheet component-slot linkage" in rendered
    assert "Worksheet manual-review items" in rendered
    assert "Worksheet follow-up queue" in rendered
    assert "Follow-up issue type" in [call["label"] for call in fake_st.selectbox_calls]
    assert "Group follow-up rows by issue type" in [call["label"] for call in fake_st.checkbox_calls]
    assert "missing_provenance" in rendered
    assert "weak_or_unreviewed_evidence" in rendered
    assert "add or confirm source/provenance documentation" in rendered
    assert "Worksheet blocked-output boundary categories" in rendered
    assert "Source traceability" in rendered
    assert "Manual-review boundary note" in rendered
    assert "EV-1" in rendered
    assert "COMP-1" in rendered
    assert "missing_provenance_or_source" in rendered
    assert "protocol" in rendered
    assert "yield_prediction" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_handoff_preview_section_filters_followup_queue_without_mutating_payload(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.selectbox_values["handoff_preview_r124_followup_type_filter"] = "weak_or_unreviewed_evidence"
    fake_st.checkbox_values["handoff_preview_r124_followup_group_by_type"] = False
    monkeypatch.setattr(section, "st", fake_st)
    payload = _handoff_payload()
    before = deepcopy(payload["plant_evidence_review_worksheet"]["followup_queue_section"])

    section.render_plant_review_handoff_preview_section(payload)
    followup_frames = [
        frame
        for frame in fake_st.dataframes
        if hasattr(frame, "columns") and "followup_type" in [str(column) for column in frame.columns]
    ]
    rendered = "\n".join(frame.to_string(index=False) for frame in followup_frames)

    assert payload["plant_evidence_review_worksheet"]["followup_queue_section"] == before
    assert len(followup_frames) == 1
    assert "weak_or_unreviewed_evidence" in rendered
    assert "EV-2" in rendered
    assert "confirm evidence level and review status" in rendered
    assert "missing_provenance" not in rendered
    assert "add or confirm source/provenance documentation" not in rendered
    assert any("1 of 2 worksheet follow-up rows shown" in message for message in fake_st.caption_messages)


def test_handoff_preview_section_preserves_zero_counts_in_handoff_readback(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    payload = _handoff_payload()
    payload["evidence_worksheet_handoff_readback"]["summary"]["weak_or_unreviewed_evidence_count"] = 0

    section.render_plant_review_handoff_preview_section(payload)

    readback_frame = next(
        frame
        for frame in fake_st.dataframes
        if hasattr(frame, "columns")
        and {"Field", "Readback"}.issubset({str(column) for column in frame.columns})
        and "Weak or unreviewed evidence" in set(frame["Field"])
    )
    row = readback_frame.loc[readback_frame["Field"] == "Weak or unreviewed evidence"].iloc[0]

    assert row["Readback"] == "0"


def test_handoff_preview_section_handles_empty_payload(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    section.render_plant_review_handoff_preview_section({})

    assert "Handoff preview" in [str(call["body"]).strip("*") for call in fake_st.markdown_calls]
    assert any("No required review items" in message for message in fake_st.info_messages)
    rendered = "\n".join(
        [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )
    assert "Evidence worksheet handoff readback" in rendered
    assert "Route-to-construct traceability readback" in rendered
    assert "Route-to-construct links" in rendered
    assert any("No route-to-construct traceability rows are available yet" in message for message in fake_st.info_messages)
    assert any("No construct draft slot rows are available yet" in message for message in fake_st.info_messages)
    assert "evidence incomplete" in rendered
    assert any("No worksheet evidence rows" in message for message in fake_st.info_messages)
    assert any("No worksheet follow-up queue items are available yet" in message for message in fake_st.info_messages)
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_handoff_preview_section_reuses_mounted_worksheet_without_local_row_shaping() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py").read_text(
        encoding="utf-8"
    )

    assert "plant_evidence_review_worksheet" in source
    assert "EVIDENCE_REVIEW_COLUMNS" not in source
    assert "COMPONENT_SLOT_COLUMNS" not in source
    assert "MANUAL_REVIEW_COLUMNS" not in source


def test_handoff_preview_section_reuses_mounted_route_construct_payload_without_local_trace_row_shaping() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py").read_text(
        encoding="utf-8"
    )

    assert "route_construct_traceability_readback" in source
    assert "build_plant_route_construct_traceability_readback" not in source
    assert "TRACEABILITY_ROW_KEYS" not in source


def test_handoff_preview_section_copy_keeps_safety_boundary() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py").read_text(
        encoding="utf-8"
    )
    test_source = (ROOT / "tests" / "test_plant_review_handoff_preview_section.py").read_text(encoding="utf-8")
    text = f"{source}\n{test_source}".casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text
    assert "documentation-only" in text
    assert "read-only" in text


def test_handoff_preview_section_copy_has_no_ranking_recommendation_or_wet_lab_ready_wording() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py").read_text(
        encoding="utf-8"
    )
    text = source.casefold()

    for phrase in ("ranking", "priority scoring", _term("recommended ", "component"), _term("wet-lab ", "ready")):
        assert phrase not in text
