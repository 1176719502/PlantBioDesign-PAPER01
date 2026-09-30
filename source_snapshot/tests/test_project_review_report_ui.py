from __future__ import annotations

import os
import re
from pathlib import Path
from types import SimpleNamespace

from core.session_keys import SK
from services.project_review_report_service import build_project_review_report
from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section
import views.pathway_workspace_sections.step2_component_context_session as step2_context_session

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_REVIEW_REPORT_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_review_report_section.py"
STEP2_CONTEXT_SESSION_HELPER = ROOT / "views" / "pathway_workspace_sections" / "step2_component_context_session.py"
PROJECT_OUTPUT_BOUNDARY_COPY = ROOT / "services" / "project_output_boundary_copy.py"


def _source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            PATHWAY_WORKSPACE,
            PROJECT_REVIEW_REPORT_SECTION,
            STEP2_CONTEXT_SESSION_HELPER,
            PROJECT_OUTPUT_BOUNDARY_COPY,
        ]
    )


def test_current_step2_component_context_helper_reads_session_without_mutating(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    session = SimpleNamespace(
        host="E.coli BL21(DE3)",
        tag="His6",
        elements={"promoter_name": "T7 promoter"},
    )
    fake_st.session_state[SK.DESIGN_SESSION] = session
    before = dict(fake_st.session_state)
    captured: dict[str, object] = {}

    monkeypatch.setattr(step2_context_session, "st", fake_st)
    monkeypatch.setattr(
        step2_context_session.presenter,
        "build_step2_component_context_readback",
        lambda **kwargs: _capture_step2_kwargs(captured, kwargs),
    )

    context = step2_context_session.current_step2_component_context_readback()

    assert context["rows"][0]["asset_id"] == "promoter-1"
    assert captured["kwargs"]["host"] == "E.coli BL21(DE3)"
    assert captured["kwargs"]["tag"] == "His6"
    assert captured["kwargs"]["elements"] == {"promoter_name": "T7 promoter"}
    assert fake_st.session_state == before


def test_current_step2_component_context_helper_missing_session_returns_none(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(step2_context_session, "st", fake_st)

    assert step2_context_session.current_step2_component_context_readback() is None
    assert fake_st.session_state == {}


def test_project_review_report_ui_passes_current_step2_context(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    step2_context = {
        "rows": [{"category": "promoter", "asset_id": "promoter-ui"}],
        "summary": {"total_rows": 1, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 0},
        "documentation_boundary_note": "Step 2 current-session documentation-only review context.",
    }
    captured: dict[str, object] = {}

    def _build_report(*args, **kwargs):
        captured["step2_component_context"] = kwargs.get("step2_component_context")
        return build_project_review_report(*args, **kwargs)

    monkeypatch.setattr(
        review_report_section,
        "current_step2_component_context_readback",
        lambda: step2_context,
    )
    monkeypatch.setattr(review_report_section, "build_project_review_report", _build_report)

    review_report_section.render_project_review_report_section(
        project={"id": 244, "name": "R244 report UI"},
        steps=[],
        linked_catalog_assets=[],
    )

    assert captured["step2_component_context"] is step2_context
    rendered = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Step 2 recorded Component Library context appendix" in rendered
    assert "promoter-ui" in rendered
    assert "step2_component_context" not in fake_st.session_state


def test_project_review_report_ui_missing_step2_context_uses_safe_empty_appendix(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    captured: dict[str, object] = {}

    def _build_report(*args, **kwargs):
        captured["step2_component_context"] = kwargs.get("step2_component_context")
        return build_project_review_report(*args, **kwargs)

    monkeypatch.setattr(
        review_report_section,
        "current_step2_component_context_readback",
        lambda: None,
    )
    monkeypatch.setattr(review_report_section, "build_project_review_report", _build_report)

    review_report_section.render_project_review_report_section(
        project={"id": 245, "name": "R244 empty Step 2 context"},
        steps=[],
        linked_catalog_assets=[],
    )

    assert captured["step2_component_context"] is None
    rendered = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "No current Step 2 Component Library context is available for this review appendix." in rendered
    assert "step2_component_context" not in fake_st.session_state


def _capture_step2_kwargs(captured: dict[str, object], kwargs: dict[str, object]) -> dict[str, object]:
    captured["kwargs"] = kwargs
    return {
        "rows": [{"category": "promoter", "asset_id": "promoter-1"}],
        "summary": {"total_rows": 1},
        "documentation_boundary_note": "documentation-only review context",
    }


def test_plant_review_markdown_draft_filename_is_safe_and_deterministic() -> None:
    filename = review_report_section._safe_plant_review_markdown_draft_filename

    assert filename(
        {"name": "Ignored project fallback"},
        user_context={"project_name": "Rice Albumin Review"},
        identity={"snapshot_id": "BDS-PLANT-R310-20260630-131415"},
    ) == "plant_design_review_package_draft_rice_albumin_review.md"
    assert filename(
        {"name": "Project: Alpha/Beta?*"},
        user_context={"project_name": ""},
        identity={"snapshot_id": "BDS-PLANT-R310-20260630-131415"},
    ) == "plant_design_review_package_draft_project_alpha_beta.md"
    assert filename(
        {"name": ""},
        user_context={"project_name": ""},
        identity={"snapshot_id": "BDS-PLANT-R310-20260630-131415"},
    ) == "plant_design_review_package_draft_bds_plant_r310_20260630_131415.md"
    assert filename(
        {"name": ""},
        user_context={"project_name": "///"},
        identity={},
    ) == "plant_design_review_package_draft_runtime_preview.md"


def test_project_review_report_ui_copy_is_present() -> None:
    source = _source()
    full_text = source + "\n" + build_project_review_report({"id": 500, "name": "UI review report"}).get("markdown", "")
    report_text = build_project_review_report({"id": 500, "name": "UI review report"}).get("detailed_documentation_report_draft", {}).get("markdown", "")

    required = [
        "Project Review Report",
        "Detailed documentation report draft",
        "Generate Project Review Report",
        "Download Project Review Report (.md)",
        "Download Detailed Documentation Report Draft (.md)",
        "Download current Plant Design Review Package draft (.md)",
        "Runtime download only: this does not save a structured project record or modify package export.",
        "Re-open Plant Design Review Markdown draft for reference",
        "Paste Plant Design Review Package Markdown draft for reference",
        "Reference-only preview",
        "Not parsed into fields. Not saved as a structured project record. Does not modify current Plant Review session fields.",
        "QR/MD5, if present, is package identity text only and does not validate biological correctness.",
        "Expression construct documentation",
        "Documentation-only construct, cassette, part, linked gene, linked pathway step, promoter source-link, ",
        "and review gap context.",
        "Construct component readback records documented component labels, categories, source/reference context, ",
        "sequence availability status, and metadata gaps only. It is not validation, selection advice, or a downstream-use state decision.",
        "Documentation review summary",
        "Review-only construct documentation summary for the current Plant Design Review Package surface.",
        "review summary status",
        "documented slots",
        "missing slots",
        "manual follow-up",
        "Source/provenance coverage count",
        "Coverage label:",
        "Review action panel",
        "Read-only documentation review actions from the current construct review payload",
        "Action row",
        "Missing documentation",
        "Needs manual follow-up",
        "Source/provenance review",
        "Boundary note",
        "Construct component documentation readback",
        "This section reads back recorded construct documentation from documented component rows only.",
        "It is not validation, selection advice, or a downstream-use state decision.",
        "Construct component readback records recorded construct documentation only. They do not validate, recommend, or decide downstream-use state.",
        "Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status.",
        "No construct component documentation rows are recorded for this report.",
        "No construct component documentation rows are recorded in this report markdown readback.",
        "No active pathway project selected.",
        "Select a pathway documentation workspace to generate a Project Review Report.",
        "Documentation-only report for review records and computational previews.",
        "Documentation report draft for the research to catalog to design to review to report workflow.",
        "Human review required; source review needed for draft research and catalog context.",
        "provenance context, traceability summary, data completeness review, human review questions",
        "local, read-only, documentation-only Project Outputs review surface for manual review",
        "not a biology-use recommendation, validation claim, " + "optimi" + "zation claim, or wet-lab use judgment",
        "does not recommend, rank, score, validate, " + "opti" + "mize, predict, or judge downstream-use state",
        "Host / chassis documentation context",
        "Read-only host / chassis context readback for chassis-neutral project review documentation.",
        "Host / chassis context readback is documentation context only.",
        "Supported chassis-neutral contexts:",
        "Contexts present in readback:",
        "Candidate Evidence Human Review Queue",
        "Read-only documentation, provenance, and manual follow-up context for candidate evidence rows",
        "visible in the project review report.",
        "This section supports manual documentation review only.",
        "It does not rank, recommend, validate, tune, or confirm biological suitability.",
        "queue items",
        "source/provenance gaps",
        "metadata needs review",
        "manual follow-up",
        "Project Review Follow-up Index",
        "Aggregates documentation and provenance follow-up items from project review queues. Review next: ",
        "total follow-up items",
        "candidate evidence items",
        "Component Library promoter asset items",
        "Follow-up id",
        "Source section",
        "Item label",
        "Manual review context",
        "Queue item id",
        "Human follow-up",
        "Source context",
        "Component Library Promoter Asset Evidence Gap Review",
        "Read-only Component Library promoter asset evidence gap review for documentation follow-up and catalog curation only.",
        "Project-linked Component Library promoter asset references are preferred when available; otherwise the section stays in a safe catalog-context empty state.",
        "promoter asset queue items",
        "promoter asset categories",
        "promoter asset references in scope",
        "Promoter label",
        "Component Library Asset Readback Report Snapshot",
        "Read-only Component Library asset readback snapshot for Project Review Report output.",
        "Reuses the generic Component Library asset readback presenter.",
        "asset rows",
        "asset types",
        "source/provenance rows",
        "Review next rows",
        "Review next: open the rows below for source/provenance, metadata, or manual follow-up context",
        "Plant Design Review Package",
        "Documentation-only plant review package skeleton/readback for plant expression construct review context.",
        "Report Identity / Verification",
        "Package type:",
        "Project direction:",
        "Report scope:",
        "Snapshot ID:",
        "MD5 checksum:",
        "QR payload:",
        "QR/MD5 verifies only the report/package snapshot identity.",
        "QR/MD5 does not validate construct readiness.",
        "QR/MD5 does not validate plant lines.",
        "QR/MD5 does not prove biological function.",
        "QR/MD5 does not predict yield.",
        "QR/MD5 does not certify experiment success.",
    ]
    for text in required:
        assert text in full_text
    for text in [
        "Linked catalog assets are documentation references only.",
        "They do not indicate biological fit, source verification, or downstream use state.",
        "Human review is required before downstream use.",
        "Expression construct documentation is documentation-only context for review and traceability.",
        "Construct component documentation readback",
        "This section reads back recorded construct documentation from documented component rows only.",
        "Construct component rows record documented labels, categories, source/reference context, sequence availability status, and review gaps only.",
        "Construct component readback is recorded construct documentation, not validation, selection advice, or a downstream-use state decision.",
        "Construct component readback records recorded construct documentation only. They do not validate, recommend, or decide downstream-use state.",
        "Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status.",
        "Promoter source links are evidence and provenance context, not selection advice.",
        "Host / chassis documentation context",
        "Host / chassis context readback is documentation context only.",
        "Component Library Asset Readback Report Snapshot",
        "Project Review Report reuses the generic Component Library asset readback presenter",
        "Plant Design Review Package",
        "Report Identity / Verification",
        "BioDesignStudioPlant",
        "PlantDesignReviewPackage",
    ]:
        assert text in report_text


def test_project_review_report_ui_avoids_forbidden_import_and_readiness_copy() -> None:
    source = _source()

    forbidden = [
        "Generate Validation Report",
        "Generate Experiment Report",
        "Generate Readiness Report",
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "ready for synthesis",
        "ready for wet lab",
        "experimentally confirmed",
        "experimentally confirmed",
        "approved",
        "compatible",
        "suitable",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
        "Ready for downstream use",
    ]
    for text in forbidden:
        assert text not in source


def test_project_review_report_section_renders_candidate_evidence_human_review_queue(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 701, "name": "Queue UI report"})
    report["candidate_evidence_human_review_queue"] = {
        "summary": {
            "queue_item_count": 4,
            "provenance_gap_count": 1,
            "metadata_gap_count": 0,
            "review_follow_up_count": 2,
        },
        "rows": [
            {
                "queue_item_id": "candidate-review-001-01",
                "candidate_label": "Queue-gap evidence row",
                "category_label": "Source/provenance gap",
                "severity_label": "high priority",
                "issue": "Missing source/provenance details",
                "human_follow_up": "Record the source identifier.",
                "source_context": "source not recorded / identifier not recorded",
            }
        ],
        "total_rows_available": 4,
        "boundary_notes": [
            "This section supports manual documentation review only.",
            "It does not rank, recommend, validate, tune, or confirm biological suitability.",
        ],
        "empty_state_message": "",
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 701, "name": "Queue UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )

    assert "Candidate Evidence Human Review Queue" in rendered
    assert "Read-only documentation, provenance, and manual follow-up context" in rendered
    assert any(call["label"] == "queue items" and call["value"] == "4" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/provenance gaps" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "metadata needs review" and call["value"] == "0" for call in fake_st.metric_calls)
    assert any(call["label"] == "manual follow-up" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "Candidate Evidence Human Review Queue" for call in fake_st.expander_calls)
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and "Queue item id" in dataframe[0]
        and dataframe[0]["Queue item id"]
        for dataframe in fake_st.dataframes
    )


def test_project_review_report_section_renders_host_chassis_context_readback(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 711, "name": "Host context UI report"})
    report["host_chassis_context_summary"] = {
        "project_context_label": "Yeast",
        "supported_contexts": [
            "bacterial",
            "yeast",
            "mammalian",
            "plant",
            "generic / unspecified",
        ],
        "contexts_present_labels": ["Yeast", "Plant"],
        "documentation_only_note": (
            "Host / chassis context readback is documentation context only. "
            "It records chassis-neutral review context and does not recommend, validate, optimize, "
            "rank, prove compatibility, or judge downstream readiness."
        ),
        "limitation_note": "Plant and Nicotiana examples may appear as examples, not as default or preferred contexts.",
        "rows": [
            {
                "source_label": "Active project host field",
                "source_value": "Pichia pastoris",
                "normalized_context_label": "Yeast",
                "asset_display_name": "Host context UI report",
            },
            {
                "source_label": "Linked host / chassis context reference",
                "source_value": "Nicotiana benthamiana documentation context",
                "normalized_context_label": "Plant",
                "asset_display_name": "Plant context note",
            },
        ],
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 711, "name": "Host context UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages)
    assert "Read-only host / chassis context readback for chassis-neutral project review documentation." in rendered
    assert "Host / chassis context readback is documentation context only." in rendered
    assert "Active project context: Yeast" in rendered
    assert any(call["label"] == "Host / chassis documentation context" for call in fake_st.expander_calls)
    assert any(
        isinstance(dataframe, list) and dataframe and dataframe[0]["Normalized context"] == "Yeast"
        for dataframe in fake_st.dataframes
    )


def test_project_review_report_section_candidate_evidence_queue_empty_state_is_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 702, "name": "Empty queue UI report"})
    report["candidate_evidence_human_review_queue"] = {
        "summary": {
            "queue_item_count": 0,
            "provenance_gap_count": 0,
            "metadata_gap_count": 0,
            "review_follow_up_count": 0,
        },
        "rows": [],
        "total_rows_available": 0,
        "boundary_notes": [
            "This section supports manual documentation review only.",
            "It does not rank, recommend, validate, tune, or confirm biological suitability.",
        ],
        "empty_state_message": "No human review follow-up items are currently queued for this report.",
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 702, "name": "Empty queue UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages).lower()
    assert any(call["label"] == "Candidate Evidence Human Review Queue" for call in fake_st.expander_calls)
    assert "manual documentation review only" in rendered
    assert "no human review follow-up items are currently queued" in rendered


def test_project_review_report_section_renders_plant_promoter_evidence_gap_review(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 703, "name": "Promoter queue UI report"})
    report["plant_promoter_evidence_gap_review"] = {
        "summary_counts": {
            "profile_count": 1,
            "queue_item_count": 3,
            "category_count": 3,
        },
        "category_counts": {
            "source_provenance_gap": 1,
            "tissue_context_gap": 1,
            "documentation_follow_up": 1,
        },
        "rows": [
            {
                "queue_item_id": "plant-promoter-gap-001::source_provenance_gap",
                "promoter_label": "Linked maize promoter review record",
                "category": "source_provenance_gap",
                "issue": "Source/provenance gap remains visible for this promoter record.",
                "human_follow_up": "Add or confirm source database or accession context for documentation review.",
                "source_context": "No source database recorded",
            }
        ],
        "total_rows_available": 3,
        "boundary_notes": [
            "Supports documentation review and human curation only.",
            "Does not recommend, rank, validate, optimize, or confirm promoter suitability.",
        ],
        "empty_state_message": "",
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 703, "name": "Promoter queue UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )

    assert "Component Library Promoter Asset Evidence Gap Review" in rendered
    assert "Read-only Component Library promoter asset evidence gap review for documentation follow-up and catalog curation only." in rendered
    assert any(call["label"] == "promoter asset queue items" and call["value"] == "3" for call in fake_st.metric_calls)
    assert any(call["label"] == "promoter asset categories" and call["value"] == "3" for call in fake_st.metric_calls)
    assert any(call["label"] == "promoter asset references in scope" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "Component Library Promoter Asset Evidence Gap Review" for call in fake_st.expander_calls)
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and "Promoter label" in dataframe[0]
        and dataframe[0]["Promoter label"]
        for dataframe in fake_st.dataframes
    )


def test_project_review_report_section_renders_follow_up_index(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 705, "name": "Follow-up index UI report"})
    report["project_review_follow_up_index"] = {
        "summary": {
            "total_follow_up_items": 3,
            "source_section_counts": {
                "candidate_evidence": 1,
                "plant_promoter_catalog": 2,
            },
            "category_counts": {
                "Documentation gap": 1,
                "source_provenance_gap": 1,
                "documentation_follow_up": 1,
            },
        },
        "rows": [
            {
                "follow_up_id": "candidate_evidence::candidate-review-001-01",
                "source_section": "candidate_evidence",
                "item_label": "Candidate follow-up row",
                "category": "Documentation gap",
                "issue": "Documentation review remains available for confirmation.",
                "human_follow_up": "Confirm the recorded documentation context during manual review if needed.",
                "manual_review_context": "Plant Promoter Catalog / PP-001",
            }
        ],
        "total_rows_available": 3,
        "boundary_notes": [
            "This index supports manual documentation review and triage only.",
            "It aggregates documentation and provenance follow-up items from existing read-only review queues.",
        ],
        "empty_state_message": "",
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 705, "name": "Follow-up index UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )

    assert "Project Review Follow-up Index" in rendered
    assert any(call["label"] == "total follow-up items" and call["value"] == "3" for call in fake_st.metric_calls)
    assert any(call["label"] == "candidate evidence items" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "Component Library promoter asset items" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "Project Review Follow-up Index" and call["expanded"] is True for call in fake_st.expander_calls)
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and "Follow-up id" in dataframe[0]
        and dataframe[0]["Follow-up id"]
        for dataframe in fake_st.dataframes
    )


def test_project_review_report_section_renders_construct_component_readback(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 707, "name": "Construct component UI report"})
    report["expression_construct_documentation"] = {
        "project_scoped_filtering": "project-level construct links",
        "message": "",
        "boundary_notes": [
            "Expression construct documentation is documentation-only context for review and traceability.",
            "Construct component rows record documented labels, categories, source/reference context, sequence availability status, and review gaps only.",
        ],
        "supported_component_vocabulary": [
            "promoter",
            "5' UTR",
            "RBS",
            "coding sequence",
            "terminator",
            "other documented component",
        ],
        "construct_component_rows": [
            {
                "component_label": "Doc promoter",
                "component_category": "promoter",
                "component_reference_label": "Source reference A",
                "sequence_availability_status": "Sequence availability recorded through linked source/reference context",
                "conservation_review_evidence": "source context: Source reference A",
                "conservation_follow_up_cue": "Conservation-related source/evidence context recorded for manual documentation review",
                "review_metadata_status": "Source/reference metadata recorded for documentation review",
                "review_note": "Recorded for traceability review.",
                "cassette_label": "Cassette A",
            }
        ],
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 707, "name": "Construct component UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages)
    assert "Construct component readback records documented component labels, categories, source/reference context" in rendered
    assert "Supported documented component vocabulary: promoter, 5' UTR, RBS, coding sequence, terminator, other documented component" in rendered
    assert any(call["label"] == "Expression construct documentation" for call in fake_st.expander_calls)
    component_tables = [
        dataframe
        for dataframe in fake_st.dataframes
        if isinstance(dataframe, list)
        and dataframe
        and isinstance(dataframe[0], dict)
        and "Component label" in dataframe[0]
    ]
    assert component_tables
    assert component_tables[0][0]["Component label"] == "Doc promoter"
    assert component_tables[0][0]["Component category"] == "promoter"
    assert component_tables[0][0]["Sequence availability"] == "Sequence availability recorded through linked source/reference context"


def test_project_review_report_section_renders_component_library_asset_snapshot(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 708, "name": "Asset snapshot UI report"})
    report["component_library_asset_readback_snapshot"] = {
        "status": "AVAILABLE",
        "summary": {
            "total_asset_rows": 2,
            "asset_type_count": 2,
            "rows_with_source_provenance_identity": 2,
        },
        "rows": [
            {
                "Asset label": "Generic asset row",
                "Asset type": "promoter",
                "Domain/chassis context": "generic source context",
                "Source/provenance identity": "Local Design Asset Catalog; generic-asset",
                "Evidence/review metadata": "human review needed",
                "Next documentation review action": "Review or record evidence/review metadata.",
                "Documentation context note": (
                    "Documentation context: Project Review Report snapshot; "
                    "origin: Project documentation reference; role: report_context; "
                    "link state: Linked catalog reference. "
                    "Source/provenance identity remains Local Design Asset Catalog / generic-asset."
                ),
                "Documentation boundary note": "Documentation-only Component Library asset readback.",
            }
        ],
        "total_rows_available": 2,
        "presenter_reuse_note": (
            "Project Review Report reuses the generic Component Library asset readback presenter "
            "without adding a universal asset database model."
        ),
        "boundary_notes": [
            "Component Library asset readback snapshot is documentation-only report context.",
            "Construct component rows are documentation records only, not biological proof records.",
        ],
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 708, "name": "Asset snapshot UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )

    assert "Read-only Component Library asset readback snapshot for Project Review Report output." in rendered
    assert "without adding a universal asset database model" in rendered
    assert "documentation-only report context" in rendered
    assert any(call["label"] == "Component Library Asset Readback Report Snapshot" for call in fake_st.expander_calls)
    assert any(call["label"] == "asset rows" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "asset types" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/provenance rows" and call["value"] == "2" for call in fake_st.metric_calls)
    assert "Review next rows: 0" in rendered
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and isinstance(dataframe[0], dict)
        and dataframe[0].get("Asset label") == "Generic asset row"
        and dataframe[0].get("Documentation context note", "").startswith("Documentation context:")
        for dataframe in fake_st.dataframes
    )


def test_project_review_report_section_renders_r317_manual_plant_context_preview(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 317, "name": "R317 manual plant review"}
    fake_st.text_input_values.update(
        {
            "r317_plant_review_context_317_project_name": "R317 manual plant review",
            "r317_plant_review_context_317_target_product": "Albumin documentation target",
            "r317_plant_review_context_317_plant_species": "Oryza sativa review context",
            "r317_plant_review_context_317_target_tissue": "",
            "r317_plant_review_context_317_expression_mode": "plant molecular farming documentation context",
            "r317_plant_review_context_317_gene_cds_source": "local CDS source record",
            "r317_plant_review_context_317_plant_promoter": "",
            "r317_plant_review_context_317_utr_kozak": "not recorded",
            "r317_plant_review_context_317_signal_transit_targeting": "signal peptide note",
            "r317_plant_review_context_317_terminator": "terminator source record",
            "r317_plant_review_context_317_selectable_marker_reporter": "",
            "r317_plant_review_context_317_vector_backbone": "backbone source record",
            "r317_plant_review_context_317_transformation_context": "documentation context only",
        }
    )
    fake_st.text_area_values.update(
        {
            "r317_plant_review_context_317_evidence_provenance_notes": "source/provenance notes",
            "r317_plant_review_context_317_manual_follow_up_notes": "review source records before handoff",
        }
    )
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    input_labels = [call["label"] for call in fake_st.text_input_calls + fake_st.text_area_calls]
    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[str(call["body"]) for call in fake_st.code_calls],
            *[str(call["value"]) for call in fake_st.text_area_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[str(table) for table in fake_st.dataframes],
        ]
    )

    for expected_label in [
        "Project name",
        "Target product / protein",
        "Plant species / host context",
        "Target tissue / organ / expression compartment",
        "Gene / CDS source provenance",
        "Plant promoter context",
        "Manual follow-up notes",
    ]:
        assert expected_label in input_labels

    for expected in [
        "Manual plant review context input",
        "Plant Design Review Package preview from manual context",
        "Session-only preview: these fields are not saved as a structured project record.",
        "Plant Design Review Package preview is documentation-only and review-only.",
        "QR/MD5 verifies only Plant Design Review Package preview identity, not biological validity.",
        "source/provenance gaps",
        "Manual context readback",
        "Source/provenance gaps",
        "Package identity for this preview",
        "Copyable Plant Design Review Package draft",
        "Runtime-only Markdown draft from the current manual context.",
        "Runtime download only: this does not save a structured project record or modify package export.",
        "Re-open Plant Design Review Markdown draft for reference",
        "Reference-only preview",
        "Not parsed into fields. Not saved as a structured project record. Does not modify current Plant Review session fields.",
        "QR/MD5, if present, is package identity text only and does not validate biological correctness.",
        "Paste a Plant Design Review Package Markdown draft to display it as reference text only.",
        "# Plant Design Review Package Draft",
        "## Documentation-only boundary",
        "Project name: R317 manual plant review",
        "Plant species / host context: Oryza sativa review context",
        "Plant promoter context: NOT_AVAILABLE",
        "## Source/provenance gaps",
        "## Package identity",
        "## QR/MD5 identity-only warning",
        "Snapshot ID:",
        "MD5 checksum:",
        "BioDesignStudioPlant",
        "PlantDesignReviewPackage",
        "Albumin documentation target",
        "Plant promoter context",
        "Missing or placeholder source/provenance context.",
    ]:
        assert expected in rendered

    draft_text_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Design Review Package Markdown draft"
    )
    draft = draft_text_area["value"]
    assert "Plant Design Review Package preview is documentation-only and review-only." in draft
    assert "QR/MD5 verifies package identity only." in draft
    assert re.search(r"MD5 checksum: [0-9a-f]{32}", draft)
    assert "QR payload: BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=" in draft
    assert "Source/provenance gaps" in draft
    download_call = next(
        call
        for call in fake_st.download_button_calls
        if call["label"] == "Download current Plant Design Review Package draft (.md)"
    )
    assert download_call["data"] == draft
    assert download_call["mime"] == "text/markdown"
    assert download_call["file_name"] == "plant_design_review_package_draft_r317_manual_plant_review.md"
    assert download_call["file_name"].endswith(".md")
    assert "Albumin documentation target" in download_call["data"]
    assert "Plant promoter context: Missing or placeholder source/provenance context." in download_call["data"]
    assert "QR payload: BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=" in download_call["data"]

    assert any(call["label"] == "Plant Design Review Package" for call in fake_st.expander_calls)
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and isinstance(dataframe[0], dict)
        and "Field" in dataframe[0]
        and "Readback" in dataframe[0]
        for dataframe in fake_st.dataframes
    )
    assert any(
        isinstance(dataframe, list)
        and dataframe
        and isinstance(dataframe[0], dict)
        and "Issue" in dataframe[0]
        and "Manual follow-up" in dataframe[0]
        for dataframe in fake_st.dataframes
    )

    for forbidden in [
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
    ]:
        assert forbidden not in rendered.lower()


def test_project_review_report_section_r322_reopens_markdown_as_reference_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 322, "name": "Current runtime project"}
    fake_st.text_input_values.update(
        {
            "r317_plant_review_context_322_project_name": "Current runtime plant review",
            "r317_plant_review_context_322_target_product": "Current runtime target",
            "r317_plant_review_context_322_plant_species": "Current plant context",
            "r317_plant_review_context_322_target_tissue": "Current tissue context",
            "r317_plant_review_context_322_expression_mode": "Current expression context",
            "r317_plant_review_context_322_gene_cds_source": "Current CDS source",
            "r317_plant_review_context_322_plant_promoter": "Current promoter source",
            "r317_plant_review_context_322_utr_kozak": "Current UTR note",
            "r317_plant_review_context_322_signal_transit_targeting": "Current targeting note",
            "r317_plant_review_context_322_terminator": "Current terminator source",
            "r317_plant_review_context_322_selectable_marker_reporter": "Current marker note",
            "r317_plant_review_context_322_vector_backbone": "Current backbone source",
            "r317_plant_review_context_322_transformation_context": "Current transformation documentation context",
        }
    )
    pasted_markdown = "\n".join(
        [
            "# Plant Design Review Package Draft",
            "",
            "## Project context",
            "- Project name: Pasted archived plant review",
            "- Target product / protein: Pasted archived target",
            "",
            "## Package identity",
            "- MD5 checksum: 00000000000000000000000000000000",
            "- QR payload: BioDesignStudioPlant|PlantDesignReviewPackage|snapshot=PASTED|md5=00000000000000000000000000000000",
        ]
    )
    fake_st.text_area_values.update(
        {
            "r317_plant_review_context_322_evidence_provenance_notes": "Current evidence notes",
            "r317_plant_review_context_322_manual_follow_up_notes": "Current follow-up notes",
            "r322_plant_review_markdown_reference_322": pasted_markdown,
        }
    )
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    session_context = fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY]["322"]
    draft_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Design Review Package Markdown draft"
    )
    reference_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Paste Plant Design Review Package Markdown draft for reference"
    )
    download_call = next(
        call
        for call in fake_st.download_button_calls
        if call["label"] == "Download current Plant Design Review Package draft (.md)"
    )
    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[str(call["body"]) for call in fake_st.code_calls],
        ]
    )

    assert reference_area["value"] == ""
    assert session_context["project_name"] == "Current runtime plant review"
    assert session_context["target_product"] == "Current runtime target"
    assert session_context["plant_promoter"] == "Current promoter source"
    assert "Project name: Current runtime plant review" in draft_area["value"]
    assert "Target product / protein: Current runtime target" in draft_area["value"]
    assert "Pasted archived plant review" not in draft_area["value"]
    assert "Pasted archived target" not in draft_area["value"]
    assert download_call["data"] == draft_area["value"]
    assert "Pasted archived plant review" not in download_call["data"]
    assert "# Plant Design Review Package Draft" in rendered
    assert "Pasted archived plant review" in rendered
    assert "Reference-only preview" in rendered
    assert "Not parsed into fields" in rendered
    assert "Not saved as a structured project record" in rendered
    assert "Does not modify current Plant Review session fields" in rendered
    assert "QR/MD5, if present, is package identity text only and does not validate biological correctness." in rendered

    for forbidden in [
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
    ]:
        assert forbidden not in rendered.lower()


def test_project_review_report_section_preserves_plant_context_in_session_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {
        "id": 319,
        "name": "Project object fallback",
        "target_product": "Project object target",
    }
    fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY] = {
        "319": {
            "project_name": "Persisted plant review context",
            "target_product": "Persisted albumin target",
            "plant_species": "Persisted Oryza context",
            "target_tissue": "persisted seed context",
            "expression_mode": "persisted expression documentation context",
            "gene_cds_source": "persisted CDS source",
            "plant_promoter": "persisted promoter source",
            "utr_kozak": "persisted UTR note",
            "signal_transit_targeting": "persisted targeting note",
            "terminator": "persisted terminator source",
            "selectable_marker_reporter": "persisted marker note",
            "vector_backbone": "persisted backbone source",
            "transformation_context": "persisted transformation documentation context",
            "evidence_provenance_notes": "persisted evidence notes",
            "manual_follow_up_notes": "persisted follow-up notes",
        }
    }
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    project_name_input = next(call for call in fake_st.text_input_calls if call["label"] == "Project name")
    promoter_input = next(call for call in fake_st.text_input_calls if call["label"] == "Plant promoter context")
    follow_up_area = next(call for call in fake_st.text_area_calls if call["label"] == "Manual follow-up notes")
    draft_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Design Review Package Markdown draft"
    )
    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(table) for table in fake_st.dataframes],
            str(draft_area["value"]),
        ]
    )

    assert project_name_input["value"] == "Persisted plant review context"
    assert promoter_input["value"] == "persisted promoter source"
    assert follow_up_area["value"] == "persisted follow-up notes"
    assert "Persisted albumin target" in rendered
    assert "persisted promoter source" in rendered
    assert "Manual follow-up notes: persisted follow-up notes" in draft_area["value"]
    assert "Project object fallback" not in draft_area["value"]
    assert "Session-only preview: these fields are not saved as a structured project record." in rendered


def test_project_review_report_section_writes_plant_context_updates_to_session_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 320, "name": "R319 update source"}
    fake_st.text_input_values.update(
        {
            "r317_plant_review_context_320_project_name": "Updated session plant review",
            "r317_plant_review_context_320_target_product": "Updated target",
            "r317_plant_review_context_320_plant_species": "",
            "r317_plant_review_context_320_target_tissue": "updated tissue",
            "r317_plant_review_context_320_expression_mode": "updated expression context",
            "r317_plant_review_context_320_gene_cds_source": "updated CDS source",
            "r317_plant_review_context_320_plant_promoter": "",
            "r317_plant_review_context_320_utr_kozak": "updated UTR",
            "r317_plant_review_context_320_signal_transit_targeting": "updated targeting",
            "r317_plant_review_context_320_terminator": "updated terminator",
            "r317_plant_review_context_320_selectable_marker_reporter": "updated marker",
            "r317_plant_review_context_320_vector_backbone": "updated backbone",
            "r317_plant_review_context_320_transformation_context": "updated transformation documentation context",
        }
    )
    fake_st.text_area_values.update(
        {
            "r317_plant_review_context_320_evidence_provenance_notes": "updated evidence notes",
            "r317_plant_review_context_320_manual_follow_up_notes": "updated follow-up notes",
        }
    )
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    session_context = fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY]["320"]
    draft_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Design Review Package Markdown draft"
    )
    rendered_tables = "\n".join(str(table) for table in fake_st.dataframes)

    assert session_context["project_name"] == "Updated session plant review"
    assert session_context["target_product"] == "Updated target"
    assert session_context["plant_promoter"] == ""
    assert "Project name: Updated session plant review" in draft_area["value"]
    assert "Target product / protein: Updated target" in draft_area["value"]
    assert "Plant species / host context: Missing or placeholder source/provenance context." in draft_area["value"]
    assert "Plant promoter context: Missing or placeholder source/provenance context." in draft_area["value"]
    assert "Missing or placeholder source/provenance context." in rendered_tables
    assert any(
        call["label"] == "source/provenance gaps" and int(call["value"]) >= 2
        for call in fake_st.metric_calls
    )


def test_project_review_report_section_renders_r325_candidate_route_matrix(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 325, "name": "R325 route matrix project"}
    fake_st.text_input_values.update(
        {
            "r325_route_decision_matrix_325_0_route_label": "Route A documentation row",
            "r325_route_decision_matrix_325_0_route_type": "Plant expression construct review",
            "r325_route_decision_matrix_325_0_plant_host_context": "Oryza sativa documentation context",
            "r325_route_decision_matrix_325_0_tissue_or_compartment_context": "seed tissue review context",
            "r325_route_decision_matrix_325_0_expression_mode_context": "stable expression documentation context",
        }
    )
    fake_st.text_area_values.update(
        {
            "r325_route_decision_matrix_325_0_component_context_summary": "promoter/CDS/terminator records linked for review",
            "r325_route_decision_matrix_325_0_linked_evidence_notes": "local source records and literature notes recorded",
            "r325_route_decision_matrix_325_0_route_risk_notes": "source lineage requires manual review",
            "r325_route_decision_matrix_325_0_missing_information": "review provenance fields before handoff",
            "r325_route_decision_matrix_325_0_manual_follow_up": "Review source/provenance notes with project reviewer.",
            "r325_route_decision_matrix_325_0_decision_rationale": "Human reviewer kept this row for package drafting.",
            "r325_route_decision_matrix_325_0_rejection_rationale": "",
        }
    )
    fake_st.selectbox_values["r325_route_decision_matrix_325_0_decision_status"] = (
        "Selected for documentation follow-up"
    )
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    session_rows = fake_st.session_state[review_report_section.PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY]["325"]
    snapshot_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Candidate Route Decision Matrix Markdown snapshot"
    )
    workspace_snapshot_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Route Review Workspace Markdown snapshot"
    )
    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[str(call["value"]) for call in fake_st.text_area_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[str(table) for table in fake_st.dataframes],
        ]
    )

    assert session_rows[0]["route_label"] == "Route A documentation row"
    assert session_rows[0]["decision_status"] == "Selected for documentation follow-up"
    assert "Plant candidate route decision matrix" in rendered
    assert "Session-only candidate route review rows for documentation follow-up." in rendered
    assert "Documentation-only candidate route review" in rendered
    assert "candidate route rows: 1" in rendered
    assert "documentation follow-up: 1" in rendered
    assert "Route A documentation row" in rendered
    assert "Selected for documentation follow-up" in rendered
    assert "Copyable candidate route matrix snapshot" in rendered
    assert "Route-linked evidence cards" in rendered
    assert "Route-to-component traceability" in rendered
    assert "Copyable route review workspace snapshot" in rendered
    assert "# Plant Candidate Route Decision Matrix Snapshot" in snapshot_area["value"]
    assert "does not save structured project records" in snapshot_area["value"]
    assert "# Plant Route Review Workspace Snapshot" in workspace_snapshot_area["value"]
    assert "## Evidence cards" in workspace_snapshot_area["value"]
    assert "## Component traceability" in workspace_snapshot_area["value"]
    assert "Route A documentation row" in workspace_snapshot_area["value"]

    for forbidden in [
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "wet-lab ready",
    ]:
        assert forbidden not in rendered.lower()


def test_project_review_report_section_clear_r325_matrix_resets_only_route_namespace(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 326, "name": "Fallback route matrix project"}
    fake_st.session_state[review_report_section.PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY] = {
        "326": [
            {
                "route_label": "Should be cleared",
                "route_type": "Plant expression construct review",
                "plant_host_context": "Cleared host context",
                "tissue_or_compartment_context": "",
                "expression_mode_context": "",
                "component_context_summary": "",
                "linked_evidence_notes": "Cleared evidence notes",
                "route_risk_notes": "",
                "missing_information": "",
                "manual_follow_up": "Cleared follow-up",
                "decision_status": "Needs more evidence",
                "decision_rationale": "",
                "rejection_rationale": "",
            }
        ],
        "other-project": [{"route_label": "Other project remains"}],
    }
    fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY] = {
        "326": {"project_name": "Manual context remains"}
    }
    fake_st.session_state["unrelated_session_value"] = {"keep": True}
    fake_st.session_state["r325_route_decision_matrix_326_0_route_label"] = "Widget value to clear"
    fake_st.button_values["r325_clear_route_decision_matrix_326"] = True
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    route_store = fake_st.session_state[review_report_section.PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY]
    snapshot_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Candidate Route Decision Matrix Markdown snapshot"
    )
    workspace_snapshot_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Route Review Workspace Markdown snapshot"
    )

    assert route_store["326"][0]["route_label"] == "Fallback route matrix project"
    assert route_store["other-project"] == [{"route_label": "Other project remains"}]
    assert (
        fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY]["326"]["project_name"]
        == "Manual context remains"
    )
    assert fake_st.session_state["unrelated_session_value"] == {"keep": True}
    assert "r325_route_decision_matrix_326_0_route_label" not in fake_st.session_state
    assert "Should be cleared" not in snapshot_area["value"]
    assert "Fallback route matrix project" in snapshot_area["value"]
    assert "Should be cleared" not in workspace_snapshot_area["value"]
    assert "Fallback route matrix project" in workspace_snapshot_area["value"]


def test_project_review_report_section_clear_plant_context_resets_only_plant_namespace(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])

    project = {"id": 321, "name": "Fallback after clear", "target_product": "Fallback target"}
    fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY] = {
        "321": {
            "project_name": "Should be cleared",
            "target_product": "Cleared target",
            "plant_species": "Cleared species",
            "target_tissue": "Cleared tissue",
            "expression_mode": "Cleared mode",
            "gene_cds_source": "Cleared CDS",
            "plant_promoter": "Cleared promoter",
            "utr_kozak": "Cleared UTR",
            "signal_transit_targeting": "Cleared targeting",
            "terminator": "Cleared terminator",
            "selectable_marker_reporter": "Cleared marker",
            "vector_backbone": "Cleared backbone",
            "transformation_context": "Cleared transformation",
            "evidence_provenance_notes": "Cleared evidence",
            "manual_follow_up_notes": "Cleared follow-up",
        },
        "other-project": {"project_name": "Other project remains"},
    }
    fake_st.session_state["unrelated_session_value"] = {"keep": True}
    fake_st.session_state["r317_plant_review_context_321_project_name"] = "Widget value to clear"
    fake_st.button_values["r319_clear_plant_review_context_321"] = True
    report = build_project_review_report(project)
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    session_store = fake_st.session_state[review_report_section.PLANT_REVIEW_SESSION_CONTEXT_KEY]
    project_name_input = next(call for call in fake_st.text_input_calls if call["label"] == "Project name")
    target_input = next(call for call in fake_st.text_input_calls if call["label"] == "Target product / protein")
    draft_area = next(
        call
        for call in fake_st.text_area_calls
        if call["label"] == "Plant Design Review Package Markdown draft"
    )

    assert session_store["321"]["project_name"] == "Fallback after clear"
    assert session_store["321"]["target_product"] == "Fallback target"
    assert session_store["other-project"] == {"project_name": "Other project remains"}
    assert fake_st.session_state["unrelated_session_value"] == {"keep": True}
    assert "r317_plant_review_context_321_project_name" not in fake_st.session_state
    assert project_name_input["value"] == "Fallback after clear"
    assert target_input["value"] == "Fallback target"
    assert "Should be cleared" not in draft_area["value"]
    assert "Fallback after clear" in draft_area["value"]


def test_project_review_report_section_follow_up_index_empty_state_is_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 706, "name": "Empty follow-up index UI report"})
    report["project_review_follow_up_index"] = {
        "summary": {
            "total_follow_up_items": 0,
            "source_section_counts": {
                "candidate_evidence": 0,
                "plant_promoter_catalog": 0,
            },
            "category_counts": {},
        },
        "rows": [],
        "total_rows_available": 0,
        "boundary_notes": [
            "This index supports manual documentation review and triage only.",
        ],
        "empty_state_message": "No manual documentation follow-up items are currently aggregated for this project review context.",
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 706, "name": "Empty follow-up index UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages).lower()
    assert any(call["label"] == "Project Review Follow-up Index" for call in fake_st.expander_calls)
    assert "manual documentation review and triage only" in rendered
    assert "no manual documentation follow-up items are currently aggregated" in rendered


def test_project_review_report_section_plant_promoter_evidence_gap_empty_state_is_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    report = build_project_review_report({"id": 704, "name": "Empty promoter queue UI report"})
    report["plant_promoter_evidence_gap_review"] = {
        "summary_counts": {
            "profile_count": 0,
            "queue_item_count": 0,
            "category_count": 0,
        },
        "category_counts": {},
        "rows": [],
        "total_rows_available": 0,
        "boundary_notes": [
            "Supports documentation review and human curation only.",
            "Does not recommend, rank, validate, optimize, or confirm promoter suitability.",
        ],
        "empty_state_message": (
            "No Component Library promoter asset context is linked to this project review report, "
            "so no promoter evidence gap items are currently queued."
        ),
    }
    monkeypatch.setattr(review_report_section, "build_project_review_report", lambda *args, **kwargs: report)

    review_report_section.render_project_review_report_section(
        project={"id": 704, "name": "Empty promoter queue UI report"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages).lower()
    assert any(call["label"] == "Component Library Promoter Asset Evidence Gap Review" for call in fake_st.expander_calls)
    assert "human curation only" in rendered
    assert "no component library promoter asset context is linked to this project review report" in rendered
