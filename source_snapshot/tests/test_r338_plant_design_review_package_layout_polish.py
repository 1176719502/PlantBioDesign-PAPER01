# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    dataframe_text = "\n".join(
        frame.to_string(index=False) if hasattr(frame, "to_string") else str(frame)
        for frame in fake_st.dataframes
    )
    metric_text = "\n".join(f"{call['label']}: {call['value']}" for call in fake_st.metric_calls)
    return "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [call["label"] for call in fake_st.expander_calls]
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + dataframe_text.splitlines()
        + metric_text.splitlines()
    )


def _presenter_payload() -> dict[str, object]:
    return {
        "status": "construct_draft_preview_presenter_available",
        "page_title": "Plant Construct Draft Preview",
        "subtitle": "UI-safe presenter for read-only construct draft review.",
        "draft_summary_card": {
            "draft_id": "construct-draft-r338-layout-polish",
            "draft_status": "needs_manual_review",
            "manual_review_required": True,
            "safety_boundary": (
                "Read-only construct draft preview for source and manual review. It preserves "
                "draft slots, source identifiers, evidence identifiers, missing reasons, review "
                "counts, and warnings without creating final construct content or downstream-use "
                "judgments."
            ),
            "summary_lines": ["Manual review required."],
            "review_counts": {
                "slot_count": 2,
                "present_slot_count": 1,
                "missing_slot_count": 1,
                "needs_source_count": 1,
                "needs_confirmation_count": 1,
                "warning_count": 1,
                "review_item_count": 1,
            },
        },
        "status_badges": [
            {"label": "Preview status", "value": "construct_draft_preview_presenter_available", "tone": "neutral"},
            {"label": "Draft status", "value": "needs_manual_review", "tone": "neutral"},
            {"label": "Manual review", "value": "yes", "tone": "attention"},
        ],
        "slot_table": {
            "rows": [
                {
                    "display_label": "Promoter",
                    "slot_name": "promoter",
                    "role": "regulatory slot",
                    "status": "needs_source",
                    "safe_status_text": "missing source; manual review required",
                    "value": "",
                    "source_ids": ["SRC-PROMOTER-R338"],
                    "evidence_ids": ["EVID-PROMOTER-R338"],
                    "missing_reason": "promoter source evidence not provided",
                    "manual_review_required": True,
                },
                {
                    "display_label": "Vector backbone",
                    "slot_name": "vector_backbone",
                    "role": "vector backbone slot",
                    "status": "needs_confirmation",
                    "safe_status_text": "needs confirmation; manual review required",
                    "value": "recorded vector documentation context",
                    "source_ids": ["SRC-VECTOR-R338"],
                    "evidence_ids": ["EVID-VECTOR-R338"],
                    "missing_reason": "",
                    "manual_review_required": True,
                },
            ],
            "row_count": 2,
        },
        "evidence_summary": {
            "source_ids": ["SRC-PROMOTER-R338", "SRC-VECTOR-R338"],
            "evidence_ids": ["EVID-PROMOTER-R338", "EVID-VECTOR-R338"],
            "source_count": 2,
            "evidence_count": 2,
            "note": "Identifiers are displayed as supplied; no evidence is inferred.",
        },
        "missing_fields_section": {
            "rows": [
                {
                    "display_label": "Promoter",
                    "slot_name": "promoter",
                    "status": "needs_source",
                    "missing_reason": "promoter source evidence not provided",
                    "manual_review_required": True,
                }
            ],
            "manual_review_required": True,
        },
        "review_items_section": {
            "items": ["Promoter: source evidence requires manual review."],
            "review_item_count": 1,
            "manual_review_required": True,
        },
        "warnings_section": {
            "warnings": ["Construct draft remains a documentation-only review preview."],
            "warning_count": 1,
        },
        "empty_state": {"is_empty": False, "reason": "", "manual_review_required": True},
    }


def _plant_package() -> dict[str, object]:
    return {
        "boundary_notes": [
            "This Plant Design Review Package is a documentation-only skeleton/readback.",
        ],
        "identity": {
            "package_type": "Plant Design Review Package",
            "project_direction": "Plant recombinant protein / molecular farming",
            "report_scope": "Documentation-only pre-experiment design review",
            "snapshot_id": "BDS-PLANT-R338-20260701-000000",
            "md5_checksum": "0123456789abcdef0123456789abcdef",
            "qr_payload": "BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=R338",
            "qr_dependency_note": "Payload-only QR payload preview.",
            "boundary_notes": [
                "QR/MD5 verifies only the report/package snapshot identity.",
                "QR/MD5 does not validate construct readiness.",
            ],
        },
        "summary": {
            "section_count": 3,
            "not_available_count": 1,
            "manual_follow_up_count": 3,
        },
        "sections": [
            {
                "title": "Project direction",
                "readback": "Plant recombinant protein / molecular farming",
                "manual_follow_up": "Confirm the recorded plant project direction with the human reviewer.",
            },
            {
                "title": "Plant promoter context",
                "readback": "NOT_AVAILABLE",
                "manual_follow_up": "Review Plant Promoter Catalog or Component Library source/provenance context.",
            },
        ],
    }


def test_r338_package_context_and_identity_render_before_construct_preview(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r338-order", "name": "R338 package order"}
    fake_st.session_state[
        review_report_section._plant_construct_draft_preview_project_key(project)
    ] = _presenter_payload()
    package = _plant_package()

    review_report_section._render_plant_design_review_package_context(
        package,
        package["identity"],
        package["summary"],
    )
    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    review_report_section._render_plant_design_review_package_readback(package)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert rendered.index("Plant Design Review Package context") < rendered.index("Report Identity / Verification")
    assert rendered.index("Report Identity / Verification") < rendered.index("Plant Construct Draft Preview")
    assert rendered.index("Plant Construct Draft Preview") < rendered.index("Plant package readback rows and missing information")
    assert (
        "Review order: package context and identity -> expression construct workflow route preview"
        in rendered
    )
    assert "package sections: 3" in rendered
    assert "missing information fields: 1" in rendered
    assert "manual review rows: 3" in rendered
    assert "QR payload text readback: wraps long identity text for review only" in rendered


def test_r338_source_status_copy_stays_near_preview_and_readback_labels_are_safe(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r338-source", "name": "R338 source status"}
    fake_st.session_state[
        review_report_section._plant_construct_draft_preview_project_key(project)
    ] = _presenter_payload()

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    review_report_section._render_plant_design_review_package_readback(_plant_package())
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert "Preview source/provenance and status" in rendered
    assert "Readback-only source/status for the construct draft preview below" in rendered
    assert "Preview source: R333 presenter payload" in rendered
    assert "Draft ID: construct-draft-r338-layout-polish" in rendered
    assert "Plant package readback rows and missing information" in rendered
    assert "Missing information / manual review" in rendered
    assert "NOT_AVAILABLE marks missing information for manual review required" in rendered


def test_r338_safe_empty_state_remains_when_no_payload_exists(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    before = dict(fake_st.session_state)

    section = review_report_section._render_plant_construct_draft_preview_mount({"id": "r338-empty"})
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_empty"
    assert "No current construct draft presenter payload is available" in rendered
    assert "Preview source/provenance and status" not in rendered
    assert fake_st.session_state == before


def test_r338_package_frame_does_not_add_write_controls_or_unsafe_copy() -> None:
    source = (
        inspect.getsource(review_report_section._render_plant_design_review_package_context)
        + inspect.getsource(review_report_section._render_plant_design_review_package_readback)
        + inspect.getsource(review_report_section._render_plant_construct_draft_preview_source_indicator)
        + inspect.getsource(review_report_section._render_plant_construct_draft_preview_mount)
    )
    lowered = source.casefold()
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
        "codon",
    ]
    unsafe_phrases = [
        "valid" + "ated",
        "optim" + "ized",
        "ready " + "to build",
        "experimentally " + "verified",
        "recommended " + "construct",
        "guaran" + "teed",
    ]

    assert [call for call in forbidden_calls if call in lowered] == []
    assert [phrase for phrase in unsafe_phrases if phrase in lowered] == []
