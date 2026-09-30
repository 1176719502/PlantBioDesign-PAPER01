# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import json
from pathlib import Path

from services import rice_albumin_seed_review_workflow as workflow
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_handoff_preview_section as handoff_section
from views.pathway_workspace_sections import plant_review_workflow_section as workflow_section


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("recommended ", "component"),
    _term("best ", "component"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("suc", "cess"),
    _term("yield ", "pre", "diction"),
    _term("wet", "-lab", "-ready"),
    _term("wet-lab ", "ready"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("ready ", "for execution"),
)


ALLOWED_BLOCKED_LABELS = {
    "experimental_validation",
    "experimental_validation_claim",
    "yield_prediction",
    "optimization_output",
    "optimized_sequence",
    "pathway_optimization",
    "codon_optimization_output",
    "expression_success_claim",
}

ALLOWED_BOUNDARY_COPY = (
    "Editable local plant design project drafts are documentation-only user data. They record manual design notes, "
    "source/provenance references, and review gaps without automatic biological design, sequence generation, "
    "prediction, validation, optimization, lab instruction output, or downstream use judgment.",
    "No task, draft, sequence, validation, or optimization output.",
)


def _static_copy_text(*paths: Path) -> str:
    return "\n".join(
        node.value
        for path in paths
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ).casefold()


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
        + [f"{call['label']}: {call['value']}" for call in fake_st.metric_calls]
    )


def _copy_scan_value(value: object, *, key_path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _copy_scan_value(nested, key_path=(*key_path, key))
        return
    if isinstance(value, list):
        for nested in value:
            _copy_scan_value(nested, key_path=key_path)
        return
    if not isinstance(value, str):
        return

    text = value.casefold()
    if key_path and key_path[-1] in {
        "blocked_output_categories",
        "blocked_output_boundaries",
        "blocked_output_boundary_categories",
        "source_references",
    }:
        assert text in ALLOWED_BLOCKED_LABELS or not any(phrase in text for phrase in FORBIDDEN_COPY)
        return

    for phrase in FORBIDDEN_COPY:
        assert phrase not in text


def test_r134_visible_mount_renders_r133_seed_payload_in_handoff_surface(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(handoff_section, "st", fake_st)
    payload = workflow.build_rice_albumin_seed_review_workflow()

    mount = handoff_section.render_rice_albumin_seed_review_visible_mount(payload)
    rendered = _rendered_text(fake_st)
    rendered_lower = rendered.casefold()

    assert mount["visible_mount_schema_version"] == workflow.SEED_REVIEW_VISIBLE_MOUNT_SCHEMA_VERSION
    assert mount["visible_mount_batch"] == workflow.SEED_REVIEW_VISIBLE_MOUNT_BATCH
    assert mount["visible_mount_status"] == workflow.SEED_REVIEW_WORKFLOW_STATUS_READY
    assert mount["mount_label"] == "local seed-data review"
    assert mount["read_only"] is True
    assert mount["manual_review_required"] is True
    assert len(mount["seed_record_rows"]) == payload["summary"]["seed_record_count"]
    assert "Rice albumin seed review visible mount" in rendered
    assert "local seed-data review" in rendered
    assert "documentation-only" in rendered
    assert "needs manual review" in rendered
    assert "provenance gaps" in rendered_lower
    assert "Seed review summary" in rendered
    assert "Seed record readback" in rendered
    assert "Rejected seed rows" in rendered
    assert "Seed handoff readback" in rendered
    assert "Plant evidence review worksheet" in rendered
    assert "Worksheet evidence rows" in rendered
    assert "Worksheet follow-up queue" in rendered or "Worksheet follow-up queue by issue type" in rendered
    assert "Route-to-construct traceability readback" in rendered
    assert "Route-to-construct links" in rendered
    assert "r131-rice-albumin-project-intent" in rendered
    assert "r131-evidence-target-identity-placeholder" in rendered
    assert "plant_protein_expression_evidence_first_route_template" in rendered
    assert "r131-component-albumin-like-cds-source-placeholder" in rendered
    assert "gene_or_cds_source" in rendered
    assert "missing_provenance" in rendered
    assert "manual_review_required" in rendered
    assert "source/provenance placeholder missing" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_r134_visible_mount_preserves_ids_and_reuses_existing_payloads() -> None:
    source_payload = workflow.build_rice_albumin_seed_review_workflow()
    mount = workflow.build_rice_albumin_seed_review_visible_mount(source_payload)

    seed_ids = {row["record_id"] for row in mount["seed_record_rows"]}
    worksheet_ids = {
        row["evidence_item_id"]
        for row in mount["evidence_worksheet"]["evidence_review_section"]["rows"]
    }
    trace_rows = mount["route_construct_traceability"]["traceability_section"]["rows"]

    assert mount["evidence_worksheet"] == source_payload["evidence_worksheet"]
    assert mount["followup_queue_view"] == source_payload["followup_queue_view"]
    assert mount["route_construct_traceability"] == source_payload["route_construct_traceability"]
    assert mount["handoff_readback"] == source_payload["handoff_readback"]
    assert "r131-rice-albumin-project-intent" in seed_ids
    assert "r131-evidence-target-identity-placeholder" in seed_ids
    assert "r131-evidence-target-identity-placeholder" in worksheet_ids
    assert any(
        row["linked_evidence_id"] == "r131-evidence-target-identity-placeholder"
        and row["route_or_context_id"] == "plant_protein_expression_evidence_first_route_template"
        and "r131-component-albumin-like-cds-source-placeholder" in row["linked_component"]
        and "gene_or_cds_source" in row["linked_component_slot"]
        for row in trace_rows
    )


def test_r134_visible_mount_handles_empty_or_malformed_seed_payload_safely(tmp_path: Path, monkeypatch) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "route_contexts.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": [{"record_type": "RouteContext"}]}),
        encoding="utf-8",
    )
    (seed_dir / "component_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": []}),
        encoding="utf-8",
    )
    (seed_dir / "evidence_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": ["bad-row"]}),
        encoding="utf-8",
    )
    fake_st = FakeStreamlit()
    monkeypatch.setattr(handoff_section, "st", fake_st)
    source_payload = workflow.build_rice_albumin_seed_review_workflow(seed_dir)

    mount = handoff_section.render_rice_albumin_seed_review_visible_mount(source_payload)
    rendered = _rendered_text(fake_st)

    assert mount["visible_mount_status"] == workflow.SEED_REVIEW_WORKFLOW_STATUS_EMPTY
    assert mount["read_only"] is True
    assert mount["manual_review_required"] is True
    assert mount["seed_record_rows"] == []
    assert len(mount["rejected_seed_rows"]) == 2
    assert "No readable rice albumin seed review rows are available" in rendered
    assert "r132-rejected-route_contexts-001" in rendered
    assert "missing_record_id_or_record_type" in rendered
    assert "r132-rejected-evidence_records-001" in rendered
    assert "record_not_object" in rendered
    assert "No worksheet evidence rows" in rendered
    assert "Route-to-construct traceability readback" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_r134_plant_review_workflow_section_mounts_seed_review_after_handoff(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(tmp_path / "drafts"))
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[workflow_section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(workflow_section, "st", fake_st)
    monkeypatch.setattr(handoff_section, "st", fake_st)

    def _build_workflow(_workspace_state: dict) -> dict:
        return {
            "workflow_status": "manual_review_required",
            "manual_review_required": True,
            "warnings": [],
            "adapter_input": {},
            "chain_result": {
                "plant_review_package": {
                    "package_status": "manual_review_required",
                    "route_summary": {"route_id": "local-route"},
                    "construct_slot_summary": {"slots": []},
                },
                "route_draft": {"draft_status": "manual_review_required"},
            },
            "handoff_preview_payload": {"handoff_status": "manual_review_required"},
            "traceability": {
                "upstream_statuses": {},
                "adapter_traceability": {},
                "extractor_traceability": {},
            },
        }

    workflow_section.render_plant_review_workflow_section(
        project={"id": "r134", "name": "R134 visible mount"},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=_build_workflow,
    )
    rendered = _rendered_text(fake_st)

    assert "Handoff preview" in rendered
    assert "Rice albumin seed review visible mount" in rendered
    assert rendered.index("Handoff preview") < rendered.index("Rice albumin seed review visible mount")
    assert "r131-rice-albumin-project-intent" in rendered
    selectbox_keys = [call["key"] for call in fake_st.selectbox_calls]
    checkbox_keys = [call["key"] for call in fake_st.checkbox_calls]
    assert len(selectbox_keys) == len(set(selectbox_keys))
    assert len(checkbox_keys) == len(set(checkbox_keys))
    assert "handoff_preview_r124_followup_type_filter" in selectbox_keys
    assert "r134_seed_review_r124_followup_type_filter" in selectbox_keys
    assert "handoff_preview_r124_followup_group_by_type" in checkbox_keys
    assert "r134_seed_review_r124_followup_group_by_type" in checkbox_keys
    assert fake_st.button_calls == [
        {"label": "Create blank plant project draft", "key": "r224_plant_project_draft_new"},
    ]
    assert fake_st.download_button_calls == []


def test_r134_ui_consumes_service_mount_without_local_seed_row_shaping() -> None:
    handoff_source = (
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py"
    ).read_text(encoding="utf-8")
    workflow_source = (
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py"
    ).read_text(encoding="utf-8")

    assert "build_rice_albumin_seed_review_visible_mount" in handoff_source
    assert "render_rice_albumin_seed_review_visible_mount" in workflow_source
    assert "build_rice_albumin_seed_review_workflow" not in handoff_source
    assert '"record_type":' not in handoff_source
    assert '"route_or_context_id":' not in handoff_source
    assert '"evidence_ids":' not in handoff_source
    assert "SEED_REVIEW_WORKFLOW_SCHEMA_VERSION" not in handoff_source


def test_r134_visible_mount_copy_keeps_documentation_boundary() -> None:
    payload = workflow.build_rice_albumin_seed_review_visible_mount()
    _copy_scan_value(payload)

    source_text = _static_copy_text(
        ROOT / "services" / "rice_albumin_seed_review_workflow.py",
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py",
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    )
    for allowed_copy in ALLOWED_BOUNDARY_COPY:
        source_text = source_text.replace(allowed_copy.casefold(), "")
    for phrase in FORBIDDEN_COPY:
        assert phrase not in source_text
    assert "documentation-only" in source_text
    assert "manual review" in source_text
    assert "read-only" in source_text
