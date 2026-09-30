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


MATRIX_COLUMNS = [
    "Slot id",
    "Slot label",
    "Required / optional",
    "Evidence count",
    "Component count",
    "Gap flags",
    "Manual review",
    "Traceability ids",
]


def _workflow() -> dict[str, Any]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": [],
        "adapter_input": {
            "evidence_records": [{"id": "EV-1", "paper_title": "Rice albumin source"}],
            "component_records": [{"component_id": "COMP-1", "component_name": "Rice albumin CDS source"}],
        },
        "chain_result": {
            "chain_schema_version": "plant_review_workflow_chain.test",
            "chain_runner_version": "test",
            "plant_review_package": {
                "package_status": "manual_review_required",
                "route_summary": {
                    "route_id": "rice_seed_protein_expression",
                    "route_label": "Rice Seed Protein Expression",
                    "route_type": "plant_expression_vector",
                },
                "construct_slot_summary": {"slots": []},
            },
            "route_draft": {
                "draft_status": "manual_review_required",
                "required_slots": [
                    {
                        "slot_name": "promoter_slot",
                        "slot_label": "Promoter slot",
                        "status": "provided",
                        "manual_review_required": True,
                    }
                ],
            },
            "evidence_slot_match_result": {
                "slot_matches": [
                    {
                        "slot_id": "promoter_slot",
                        "slot_label": "Promoter slot",
                        "candidate_evidence": [{"record_id": "EV-1"}],
                        "manual_review_required": True,
                    }
                ]
            },
            "component_candidate_match_result": {
                "slot_matches": [
                    {
                        "slot_id": "promoter_slot",
                        "slot_label": "Promoter slot",
                        "candidate_components": [
                            {
                                "component_id": "COMP-1",
                                "provenance_status": "source_recorded_provenance_missing",
                            }
                        ],
                        "manual_review_required": True,
                    }
                ]
            },
            "gap_manual_review_queue_result": {
                "review_items": [
                    {
                        "slot_id": "promoter_slot",
                        "slot_label": "Promoter slot",
                        "category": "provenance_gap",
                        "evidence_ids": ["EV-1"],
                        "component_ids": ["COMP-1"],
                    }
                ]
            },
        },
        "handoff_preview_payload": {"handoff_status": "manual_review_required"},
        "traceability": {
            "upstream_statuses": {
                "extractor": "ready_for_adapter",
                "adapter": "ready_for_chain",
                "chain": "manual_review_required",
                "handoff": "manual_review_required",
            }
        },
    }


def _find_matrix_dataframe(fake_st: FakeStreamlit):
    for frame in fake_st.dataframes:
        if list(frame.columns) == MATRIX_COLUMNS:
            return frame
    raise AssertionError("Slot coverage matrix dataframe was not rendered")


def test_slot_coverage_matrix_mount_renders_read_only_table(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(tmp_path / "drafts"))
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)

    section.render_plant_review_workflow_section(project={"id": "R87"}, build_workflow=lambda _state: _workflow())
    rendered = "\n".join(
        fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )
    matrix_frame = _find_matrix_dataframe(fake_st)
    row = matrix_frame.to_dict("records")[0]

    assert "Slot coverage matrix" in rendered
    assert "Slot coverage matrix status: manual review required" in rendered
    assert "bds-review-grid" in rendered
    assert "Evidence count" in rendered
    assert "Component count" in rendered
    assert "Gap flags" in rendered
    assert any(call["label"] == "Full Slot coverage matrix table" for call in fake_st.expander_calls)
    assert row["Slot id"] == "promoter_slot"
    assert row["Slot label"] == "Promoter slot"
    assert row["Evidence count"] == 1
    assert row["Component count"] == 1
    assert row["Manual review"] == "yes"
    assert "provenance gap" in row["Gap flags"]
    assert "EV-1" in row["Traceability ids"]
    assert "COMP-1" in row["Traceability ids"]
    assert fake_st.button_calls == [
        {"label": "Create blank plant project draft", "key": "r224_plant_project_draft_new"},
    ]
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_slot_coverage_matrix_mount_copy_keeps_safety_boundary() -> None:
    source = (ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py").read_text(
        encoding="utf-8"
    )
    test_source = (ROOT / "tests" / "test_plant_review_slot_coverage_matrix_mount.py").read_text(encoding="utf-8")
    text = f"{source}\n{test_source}".casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text
    assert "documentation-only" in text
    assert "read-only" in text
