# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path

from services import rice_albumin_manual_provenance_verification_queue as queue
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
    _term("accepted ", "evidence"),
    _term("verified", "-ID"),
    _term("verified ", "ID"),
)

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


def _workflow_payload() -> dict[str, object]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": [],
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
                "route_summary": {"route_id": "rice_seed_route", "route_label": "Rice seed route"},
                "construct_slot_summary": {
                    "slots": [
                        {
                            "slot_id": "gene_or_cds_source",
                            "slot_label": "Gene/CDS source",
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
                    "category": "provenance_gap",
                    "slot_id": "gene_or_cds_source",
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
            "extractor_traceability": {"source_keys_used": ["project_id", "sources"]},
        },
    }


def _handoff_payload() -> dict[str, object]:
    return {
        "handoff_status": "manual_review_required",
        "manual_review_required": True,
        "reviewer_summary": {
            "status_label": "manual_review_required",
            "manual_review_required": True,
            "blocked": True,
            "review_item_count": 2,
            "review_item_categories": {"provenance_gap": 2},
            "safe_boundary_note": "Documentation-only review context.",
        },
        "required_review_items": [
            {
                "item_id": "manual-1",
                "category": "provenance_gap",
                "title": "Source review",
                "severity": "review_required",
                "slot_id": "gene_or_cds_source",
                "reason": "Source context needs manual review.",
            }
        ],
        "missing_information_items": [
            {
                "item_id": "missing-1",
                "category": "provenance_gap",
                "title": "Source/accession review",
                "severity": "review_required",
                "slot_id": "gene_or_cds_source",
                "reason": "Source/accession gap remains visible.",
            }
        ],
        "blocked_output_boundaries": ["sequence_generation"],
        "source_traceability": {
            "source_kind": "chain_result",
            "source_schema_version": "plant_review_workflow_chain.v2.7.r76",
            "route_traceability_items": [{"route_id": "rice_seed_route"}],
            "handoff_context": {"surface": "workspace"},
        },
    }


def _queue_payload() -> dict[str, object]:
    return {
        "workflow_schema_version": queue.MANUAL_PROVENANCE_QUEUE_SCHEMA_VERSION,
        "workflow_batch": queue.MANUAL_PROVENANCE_QUEUE_BATCH,
        "workflow_status": queue.MANUAL_PROVENANCE_QUEUE_STATUS_READY,
        "read_only": True,
        "manual_review_required": True,
        "queue_boundary": "Documentation-only manual provenance task. Manual review required.",
        "source_policy": (
            "No source lookup, external API calls, identifier filling, seed record changes, "
            "evidence acceptance, component selection, or record promotion."
        ),
        "summary": {
            "total_tasks": 46,
            "represented_record_count": 12,
            "records_requiring_manual_lookup": 12,
            "records_blocked_from_promotion": 12,
            "missing_source_id_count": 6,
            "missing_accession_count": 12,
            "ready_to_promote_count": 0,
            "task_type_counts": {"do_not_promote_guard": 1},
        },
        "task_types": ["do_not_promote_guard"],
        "tasks": [
            {
                "task_id": "r150-service-sentinel-task",
                "record_id": "r131-evidence-target-identity-placeholder",
                "record_type": "EvidenceRecord",
                "task_type": "do_not_promote_guard",
                "missing_fields": ["source_id", "accession"],
                "verification_question": "Which source context should a human review?",
                "blocking_reason": "Promotion remains blocked while provenance gaps are visible.",
                "required_manual_action": "Manual review in a later scoped metadata update.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            }
        ],
        "warnings": [],
    }


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
        + [f"{call['label']}: {call['value']}" for call in fake_st.metric_calls]
    )


def test_r150_plant_review_map_and_collapsed_detail_sections_render(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[workflow_section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(workflow_section, "st", fake_st)
    monkeypatch.setattr(workflow_section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(workflow_section, "render_rice_albumin_seed_review_visible_mount", lambda: {})

    workflow_section.render_plant_review_workflow_section(
        project={"id": "r150", "name": "R150 review"},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=lambda _state: _workflow_payload(),
    )
    rendered = _rendered_text(fake_st)
    expander_labels = [call["label"] for call in fake_st.expander_calls]

    assert "Plant Review section map" in rendered
    assert "Seed review" in rendered
    assert "Provenance verification" in rendered
    assert "Manual verification queue" in rendered
    assert "Route-to-construct traceability" in rendered
    assert "Handoff readback" in rendered
    assert "Workflow status summary" in rendered
    assert "Slot coverage matrix detail" in expander_labels
    assert "Evidence, component, and gap detail" in expander_labels


def test_r150_long_status_values_are_wrapped_not_metric_values(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[workflow_section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(workflow_section, "st", fake_st)
    monkeypatch.setattr(workflow_section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(workflow_section, "render_rice_albumin_seed_review_visible_mount", lambda: {})

    workflow_section.render_plant_review_workflow_section(
        project={"id": "r150", "name": "R150 review"},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=lambda _state: _workflow_payload(),
    )

    assert "manual review required" in _rendered_text(fake_st)
    assert all(call["value"] != "manual review required" for call in fake_st.metric_calls)
    assert all(call["value"] != "manual_review_required" for call in fake_st.metric_calls)

    handoff_fake = FakeStreamlit()
    monkeypatch.setattr(handoff_section, "st", handoff_fake)
    monkeypatch.setattr(
        handoff_section,
        "render_rice_albumin_manual_provenance_verification_readback",
        lambda: {"read_only": True},
    )
    monkeypatch.setattr(
        handoff_section,
        "render_rice_albumin_manual_provenance_verification_queue",
        lambda: {"read_only": True},
    )
    handoff_section.render_plant_review_handoff_preview_section(_handoff_payload())

    assert "manual review required" in _rendered_text(handoff_fake)
    assert "Handoff status" not in [call["label"] for call in handoff_fake.metric_calls]
    assert "Status label" not in [call["label"] for call in handoff_fake.metric_calls]
    assert all(call["value"] != "manual review required" for call in handoff_fake.metric_calls)


def test_r150_handoff_keeps_provenance_queue_and_service_sentinel_visible(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(handoff_section, "st", fake_st)
    monkeypatch.setattr(
        handoff_section,
        "build_rice_albumin_manual_provenance_verification_queue",
        lambda: _queue_payload(),
    )

    handoff_section.render_plant_review_handoff_preview_section(_handoff_payload())
    rendered = _rendered_text(fake_st)

    assert "Handoff review item detail" in [call["label"] for call in fake_st.expander_calls]
    assert "Rice albumin provenance verification detail" in [call["label"] for call in fake_st.expander_calls]
    assert "Rice albumin manual provenance verification" in rendered
    assert "Rice albumin manual provenance verification queue" in rendered
    assert "Total tasks" in rendered
    assert "46" in rendered
    assert "ready_to_promote_count" in rendered
    assert "r150-service-sentinel-task" in rendered
    assert "promotion_blocked" in rendered
    assert "do_not_promote_until_verified" in rendered


def test_r150_malformed_queue_still_fails_closed_without_filling_or_promoting(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(handoff_section, "st", fake_st)

    mount = handoff_section.render_rice_albumin_manual_provenance_verification_queue(
        {"workflow_status": "unexpected", "summary": "bad", "tasks": "bad"}
    )
    rendered = _rendered_text(fake_st)
    tasks = mount["manual_provenance_queue_tasks"]

    assert mount["read_only"] is True
    assert mount["manual_provenance_queue_payload"]["workflow_status"] == queue.MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
    assert mount["manual_provenance_queue_payload"]["summary"]["total_tasks"] == 1
    assert mount["manual_provenance_queue_payload"]["summary"]["ready_to_promote_count"] == 0
    assert all(task["promotion_blocked"] is True for task in tasks)
    assert all(task["do_not_promote_until_verified"] is True for task in tasks)
    assert "read-only fail-closed state" in rendered
    assert "PMID:" not in rendered
    assert "DOI:" not in rendered
    assert "database_id" not in rendered


def test_r150_changed_ui_copy_keeps_documentation_boundary() -> None:
    source_text = _static_copy_text(
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py",
    )
    for allowed_copy in ALLOWED_BOUNDARY_COPY:
        source_text = source_text.replace(allowed_copy.casefold(), "")

    for phrase in FORBIDDEN_COPY:
        assert phrase not in source_text
    assert "documentation-only" in source_text
    assert "read-only" in source_text
