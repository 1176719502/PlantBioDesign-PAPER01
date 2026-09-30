# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from services import plant_evidence_review_worksheet_presenter as worksheet_presenter
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_handoff_preview_section as handoff_section
from views.pathway_workspace_sections import plant_review_workflow_section as section


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


def _rice_albumin_project() -> dict[str, Any]:
    return {
        "id": "R88-RICE-ALBUMIN",
        "name": "Rice albumin visible review workspace",
        "target_product": "rice seed albumin-like protein",
        "target_gene": "rice albumin-like CDS",
        "host": "Oryza sativa rice",
        "expression_context": "rice seed plant expression vector context",
        "description": "Document a rice albumin-like plant expression vector review route.",
        "notes": "Local documentation workspace for manual review.",
    }


def _rice_albumin_steps() -> list[dict[str, Any]]:
    return [
        {
            "id": "R88-COMP-CDS",
            "step_name": "Albumin CDS source context",
            "gene_name": "rice albumin-like CDS",
            "organism_source": "Oryza sativa rice",
            "reaction_name": "plant expression vector documentation context",
            "notes": "Source/provenance note remains open for manual review.",
        }
    ]


def _rice_albumin_test_records() -> list[dict[str, Any]]:
    return [
        {
            "id": "R88-EV-CDS",
            "test_name": "Rice albumin source record",
            "summary": "Local source note for rice seed albumin-like protein identity review.",
            "notes": "Evidence metadata is present, while provenance gaps remain visible.",
        }
    ]


def _rendered_text(fake_st: FakeStreamlit) -> str:
    parts: list[str] = []
    parts.extend(fake_st.subheaders)
    parts.extend(fake_st.caption_messages)
    parts.extend(str(call["body"]) for call in fake_st.markdown_calls)
    parts.extend(frame.to_string(index=False) for frame in fake_st.dataframes)
    parts.extend(f"{call['label']}: {call['value']}" for call in fake_st.metric_calls)
    return "\n".join(parts)


def _find_matrix_dataframe(fake_st: FakeStreamlit):
    for frame in fake_st.dataframes:
        if list(frame.columns) == MATRIX_COLUMNS:
            return frame
    raise AssertionError("Slot coverage matrix dataframe was not rendered")


def _find_worksheet_handoff_readback_dataframe(fake_st: FakeStreamlit):
    for frame in fake_st.dataframes:
        if not hasattr(frame, "columns"):
            continue
        columns = {str(column) for column in frame.columns}
        if {"Field", "Readback"}.issubset(columns) and "Weak or unreviewed evidence" in set(frame["Field"]):
            return frame
    raise AssertionError("Evidence worksheet handoff readback dataframe was not rendered")


def test_rice_albumin_workspace_visible_workflow_flows_through_plant_review_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(tmp_path / "drafts"))
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(handoff_section, "st", fake_st)

    workflow = section.render_plant_review_workflow_section(
        project=_rice_albumin_project(),
        steps=_rice_albumin_steps(),
        expression_links=[],
        test_records=_rice_albumin_test_records(),
        review_signals=[],
    )
    rendered = _rendered_text(fake_st)
    matrix_frame = _find_matrix_dataframe(fake_st)
    matrix_rows = matrix_frame.to_dict("records")
    handoff_payload = workflow["handoff_preview_payload"]
    worksheet = handoff_payload["plant_evidence_review_worksheet"]
    readback = handoff_payload["evidence_worksheet_handoff_readback"]
    followup_section = worksheet["followup_queue_section"]
    source_followup_rows = deepcopy(followup_section["rows"])
    filter_view = worksheet_presenter.build_followup_queue_filter_view(
        followup_section,
        followup_type="missing_provenance",
    )
    filter_view["rows"][0]["followup_type"] = "changed_in_filter_view_only"
    readback_frame = _find_worksheet_handoff_readback_dataframe(fake_st)
    weak_row = readback_frame.loc[readback_frame["Field"] == "Weak or unreviewed evidence"].iloc[0]
    rendered_lower = rendered.casefold()

    assert workflow["workspace_workflow_schema_version"].startswith("plant_review_workspace_workflow")
    assert workflow["project_payload"]["project_id"] == "R88-RICE-ALBUMIN"
    assert workflow["traceability"]["upstream_statuses"]["extractor"] == "ready_for_adapter"
    assert workflow["traceability"]["upstream_statuses"]["adapter"] == "ready_for_chain"
    assert workflow["chain_result"]["chain_schema_version"].startswith("plant_review_workflow_chain")
    assert workflow["presenter_sections"]["package_header"]["package_id"]
    assert workflow["handoff_preview_payload"]["handoff_schema_version"].startswith("plant_review_handoff_data_adapter")
    assert workflow["manual_review_required"] is True

    assert "Plant Review Workflow" in rendered
    assert "Route summary" in rendered
    assert "Package status / warnings" in rendered
    assert "Handoff preview" in rendered
    assert "Slot coverage matrix" in rendered
    assert "manual review required" in rendered
    assert any(row["Evidence count"] >= 0 and row["Component count"] >= 0 for row in matrix_rows)
    assert any("evidence gap" in row["Gap flags"] for row in matrix_rows)
    assert any("provenance gap" in row["Gap flags"] for row in matrix_rows)
    assert any(row["Traceability ids"] for row in matrix_rows)

    assert worksheet["worksheet_status"] == worksheet_presenter.SUPPORTED_WORKSHEET_STATUS
    assert worksheet["read_only"] is True
    assert worksheet["plant_scope_only"] is True
    assert worksheet["evidence_review_section"]["rows"]
    assert worksheet["summary"]["total_evidence_rows"] == len(worksheet["evidence_review_section"]["rows"])
    assert worksheet["summary"]["followup_queue_count"] == len(followup_section["rows"])
    assert worksheet["summary"]["missing_source_or_provenance_count"] > 0
    assert worksheet["summary"]["manual_review_required_count"] > 0
    assert worksheet["summary"]["weak_or_unreviewed_evidence_count"] == 0
    assert weak_row["Readback"] == "0"
    assert readback["worksheet_status"] == worksheet["worksheet_status"]
    assert readback["summary"]["overall_review_state"] == worksheet["summary"]["overall_review_state"]
    assert readback["summary"]["followup_queue_count"] == worksheet["summary"]["followup_queue_count"]
    assert readback["followup_queue_status"]["total_count"] == worksheet["summary"]["followup_queue_count"]
    assert readback["followup_queue_status"]["group_counts"]
    assert "missing_provenance" in readback["followup_queue_status"]["followup_type_options"]
    assert filter_view["rows"][0]["followup_type"] == "changed_in_filter_view_only"
    assert any(row["followup_type"] == "missing_provenance" for row in filter_view["rows"][1:])
    assert followup_section["rows"] == source_followup_rows

    assert "Plant evidence review worksheet" in rendered
    assert "Worksheet summary rollup" in rendered
    assert "Worksheet follow-up queue" in rendered or "Worksheet follow-up queue by issue type" in rendered
    assert "Evidence worksheet handoff readback" in rendered
    assert "Missing source/provenance" in rendered
    assert "Manual review required" in rendered
    assert "Blocked boundary categories" in rendered
    assert "Blocked output boundary" in rendered
    assert "source/provenance placeholder missing" in rendered
    assert "manual_review_required" in rendered
    assert "boundary_only_category" in rendered

    for phrase in FORBIDDEN_COPY:
        assert phrase not in rendered_lower

    assert fake_st.button_calls == [
        {"label": "Create blank plant project draft", "key": "r224_plant_project_draft_new"},
    ]
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []
