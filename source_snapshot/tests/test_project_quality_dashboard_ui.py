from __future__ import annotations

from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_quality_dashboard_section as quality_dashboard_section

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py"
SERVICE = ROOT / "services" / "project_quality_dashboard_service.py"
HANDOFF_SERVICE = ROOT / "services" / "project_review_handoff_center_service.py"
HANDOFF_PACKAGE_PREVIEW_SERVICE = ROOT / "services" / "project_handoff_package_preview_service.py"
VALIDATION_CASE_PACKAGE_SERVICE = ROOT / "services" / "validation_case_package_service.py"
PACKAGE_TRAIL_SERVICE = ROOT / "services" / "project_package_review_trail_service.py"
QUEUE_SERVICE = ROOT / "services" / "candidate_evidence_human_review_queue.py"
EXPRESSION_CONSTRUCT_PRESENTER = ROOT / "services" / "expression_construct_presenter.py"
EXPRESSION_VECTOR_RECORD_INPUT_ADAPTER = ROOT / "services" / "expression_vector_package_record_input_adapter.py"
PROJECT_OUTPUT_BOUNDARY_COPY = ROOT / "services" / "project_output_boundary_copy.py"
PROJECT_OUTPUT_SECTION_OVERVIEW = ROOT / "services" / "project_output_section_overview.py"


R102_FORBIDDEN_CANDIDATE_MATRIX_TERMS = [
    "re" + "commended",
    "best",
    "opti" + "mal",
    "rank" + "ed",
    "scor" + "ed",
    "valid" + "ated",
    "ready " + "for wet lab",
    "compatible " + "host",
    "experimentally " + "confirmed",
    "biological " + "suitability",
]


def _source() -> str:
    return (
        PATHWAY_WORKSPACE.read_text(encoding="utf-8")
        + "\n"
        + SECTION.read_text(encoding="utf-8")
        + "\n"
        + SERVICE.read_text(encoding="utf-8")
        + "\n"
        + HANDOFF_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + HANDOFF_PACKAGE_PREVIEW_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + VALIDATION_CASE_PACKAGE_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + PACKAGE_TRAIL_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + QUEUE_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + EXPRESSION_CONSTRUCT_PRESENTER.read_text(encoding="utf-8")
        + "\n"
        + EXPRESSION_VECTOR_RECORD_INPUT_ADAPTER.read_text(encoding="utf-8")
        + "\n"
        + PROJECT_OUTPUT_BOUNDARY_COPY.read_text(encoding="utf-8")
        + "\n"
        + PROJECT_OUTPUT_SECTION_OVERVIEW.read_text(encoding="utf-8")
    )


def test_project_quality_dashboard_ui_copy_is_present() -> None:
    source = _source()

    required = [
        "Project Quality Dashboard",
        "overall documentation status",
        "pathway steps count",
        "linked artifacts count",
        "Host / Chassis Context Summary",
        "Read-only host / chassis documentation context for the active project.",
        "Supported contexts:",
        "Contexts present in current documentation:",
        "Project context label:",
        "Plant context is supported as one documentation example only",
        "saved design snapshot status",
        "export package status",
        "import safety check status",
        "review gaps count",
        "Step 2 Component Library context - manual follow-up summary",
        "Current-session review context for source/provenance review, record review status, and manual follow-up only.",
        "This summary is not counted as a Dashboard gap and is not saved as evidence.",
        "No current Step 2 Component Library context is available for this Dashboard summary.",
        "review guidance",
        "No active pathway project selected.",
        "Select a pathway documentation workspace to view the Project Quality Dashboard.",
        "local, read-only, documentation-only Project Outputs review surface for manual review",
        "This dashboard summarizes documentation completeness only.",
        "It is not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment.",
        "It does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state.",
        "It does not forecast yield.",
        "It does not tune pathways.",
        "It does not provide wet-lab instructions.",
        "Import Preview remains read-only.",
        "Blocked / NO-GO import states apply only to the gated create-as-new ",
        "Documentation Consistency / Provenance",
        "documentation consistency",
        "provenance context",
        "source/provenance review",
        "human review needed",
        "documentation review summary",
        "Summary of existing local documentation records for review context only",
        "this is not selection advice",
        "behavior forecast, source-verification, biological-fit, downstream-use, or approval decision",
        "guidance items",
        "boundary notes",
        "Package Exchange Review Trail",
        "Documentation-only trail for package export/import review context",
        "Manifest review available",
        "Record count context",
        "Workflow context",
        "Project Review Report and Project Quality Dashboard",
        "Component Library promoter asset reference summary",
        "Linked promoter asset reference count",
        "Expression Wizard catalog traceability summary",
        "Documentation-level reference count",
        "Component Library promoter asset reference count",
        "Generic Component Library asset readback",
        "Read-only generic Component Library asset readback",
        "This section reuses the Component Library presenter",
        "does not create a universal asset database model",
        "asset readback rows",
        "asset type groups",
        "source/provenance rows",
        "record review rows",
        "Candidate Evidence Review Matrix",
        "evidence review records",
        "record review complete",
        "record review gaps",
        "source trace missing",
        "Missing fields",
        "Record review status",
        "Review focus",
        "Next documentation review action",
        "Field legend:",
        "candidate_label",
        "source_category",
        "source_identifier",
        "provenance_status",
        "metadata_status",
        "review_status",
        "missing_fields",
        "next_manual_action",
        "boundary_note",
        "This matrix supports manual documentation review planning only",
        "Review Snapshot",
        "Collapsed read-only Markdown snapshot for mentor/demo walkthroughs",
        "human review support, and documentation triage only.",
        "Use this snapshot to summarize documented source trace, missing fields, and manual follow-up.",
        "It is not a candidate decision or biological proof record.",
        "Human Review Queue",
        "Collapsed read-only queue for documentation triage and human review follow-up only.",
        "This queue supports manual review only.",
        "or confirm biological use suitability.",
        "Project Review Follow-up Index",
        "Collapsed read-only follow-up summary for manual documentation triage across project review queues.",
        "total follow-up items",
        "candidate evidence items",
        "Expression construct documentation follow-up",
        "Read-only project-level queue for Expression Construct component documentation follow-up.",
        "Review full construct, cassette, component, source/reference, provenance, and review-note readback",
        "Component rows reviewed",
        "Source/reference context",
        "Missing source/reference context",
        "Sequence availability note",
        "Record review status",
        "Review note context",
        "Documentation follow-up",
        "Component label",
        "queue items",
        "source/provenance gaps",
        "metadata needs review",
        "manual follow-up",
        "Queue item id",
        "Human follow-up",
        "Source context",
        "Project review handoff center",
        "Read-only project-level handoff summary",
        "Handoff checklist",
        "construct/component source context reviewed",
        "provenance/review context reviewed",
        "evidence follow-up reviewed",
        "Component Library promoter asset source/provenance and record review status reviewed",
        "host/context documentation reviewed",
        "report markdown available for human review",
        "Follow-up queue overview",
        "Source surface",
        "Item label",
        "Issue type",
        "Manual follow-up note",
        "Review next",
        "Markdown handoff summary",
        "copy/review only",
        "no export, package, or schema changes",
        "expression construct follow-up",
        "candidate evidence follow-up",
        "Component Library promoter asset source/review follow-up",
        "host/context follow-up",
        "Project handoff package preview",
        "Expression Vector Design Package preview",
        "Expression Vector Design Package Markdown preview",
        "Current-record source readback",
        "Preview field",
        "Current value",
        "Source/readback origin",
        "Source/provenance status",
        "Target Gene / CDS / Protein",
        "Expression Host",
        "Promoter",
        "CDS / Insert",
        "Vector / Backbone",
        "Sequence Basic Checks",
        "Read-only Markdown preview for documentation review",
        "Single-gene sample walkthrough helper",
        "Learning aid only for one gene / one protein / one enzyme expression-vector preparation.",
        "Single-gene sample walkthrough readback",
        "What has been recorded:",
        "Source/provenance gaps:",
        "Manual follow-up:",
        "The sample is read-only and in-memory only.",
        "sample status",
        "sample MD5",
        "sample slot rows",
        "sample follow-up rows",
        "Documentation review only",
        "EV package status",
        "EV package MD5",
        "Expression Vector Design Package status",
        "Expression Vector Design Package MD5",
        "cassette slot rows",
        "Project handoff review workspace",
        "Handoff Review",
        "First-class read-only workspace for project handoff review surfaces",
        "Read-only workspace for mentor, collaborator, platform, or internal project documentation review.",
        "This workspace organizes local, read-only, documentation-only review surfaces for manual review.",
        "No export package is created here. No file or download is created here.",
        "Workspace Markdown map",
        "workspace areas",
        "documentation surfaces",
        "traceability rows",
        "workspace snapshot checksum",
        "QR payload status",
        "Workspace area",
        "Current status",
        "Key count or identity",
        "Review surface",
        "Where to inspect next",
        "Boundary note",
        "Handoff Center",
        "Package Preview",
        "Snapshot / MD5 / QR Payload",
        "Review Sheet Copy View",
        "Traceability Matrix",
        "Project Review Report Markdown",
        "Output sections overview",
        "Compact read-only map of Project Outputs sections for manual documentation review.",
        "sections listed",
        "available sections",
        "overview status",
        "Detailed Documentation Draft / markdown preview",
        "Quality Dashboard package preview",
        "Expression Construct Review summary/action panel",
        "Component Library follow-up queue report/readback",
        "Preview-only package preview",
        "Copy-only review sheet",
        "MD5/QR payload for preview matching only",
        "Read-only preview for human handoff review",
        "Package preview only; no export package is created here.",
        "Handoff snapshot review card",
        "Read-only snapshot identity for preview review matching.",
        "The MD5 code is for preview matching only, not a security signature or certification.",
        "Handoff QR verification preview",
        "Use this preview identity to match the same handoff snapshot during human review.",
        "Payload-only fallback is used",
        "Read-only QR verification payload",
        "QR verification payload",
        "QR checksum algorithm",
        "QR MD5 preview checksum",
        "QR included surfaces",
        "QR manual follow-up",
        "no QR rendering dependency is present",
        "preview checksum",
        "checksum algorithm",
        "included surfaces",
        "preview sections",
        "content length",
        "Snapshot included surfaces",
        "Snapshot ID:",
        "Handoff cover summary",
        "Project label/name:",
        "Total manual follow-up items:",
        "Documentation surfaces included:",
        "Included documentation preview",
        "Documentation surface",
        "construct/component documentation summary",
        "evidence follow-up summary",
        "Component Library promoter asset source/review gap summary",
        "host/context documentation summary",
        "project review report summary",
        "Manual follow-up queue",
        "Project handoff traceability matrix",
        "Read-only traceability matrix linking each documentation source",
        "documentation source",
        "manual follow-up status",
        "source/reference context",
        "provenance/review context",
        "included in review sheet",
        "matrix rows",
        "source/reference follow-up",
        "provenance/review follow-up",
        "manual follow-up items",
        "documentation surfaces included",
        "review source records before handoff",
        "review provenance notes before handoff",
        "Markdown handoff preview",
        "human review/copying",
        "Project handoff review sheet",
        "read-only review sheet",
        "copy view",
        "Markdown copy view",
        "Plain-text copy view",
        "documentation handoff review",
        "no file is generated here",
        "Review sheet sections",
        "Structured sections included in the read-only review sheet copy view.",
        "Validation Case Package",
        "Documentation-only pre-experiment package for teacher/company feasibility review.",
        "Validation case overview",
        "Candidate target protein/product/pathway",
        "Construct, evidence, codon, and conservation summaries",
        "Validation case review gaps / manual follow-up list",
        "Company feasibility feedback placeholder",
        "Experiment status placeholder",
        "Result summary placeholder",
        "Validation case package identity",
        "BioDesign Studio validation case package identity payload",
        "Validation case Markdown package",
        "Validation case plain-text package",
        "It is not a wet-lab protocol.",
        "It does not guarantee expression.",
        "It does not forecast yield or experimental success.",
        "It does not select a preferred expression system.",
        "It does not replace expert/company review.",
        "It does not perform codon rewriting or automatic conservation classification.",
    ]
    for text in required:
        assert text in source


def test_project_quality_dashboard_ui_avoids_forbidden_copy_and_execution_hooks() -> None:
    source = _source()

    forbidden = [
        "Quality Score",
        "Evidence Score",
        "Readiness Score",
        "Validation Score",
        "Experiment Ready",
        "Production Ready",
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready " + "for execution",
        "next " + "re" + "commended actions",
        "Be" + "st candidate",
        "Opti" + "mal candidate",
        "Rank" + "ed candidate",
        "Scor" + "ed candidate",
        "Valid" + "ated candidate",
        "Ready " + "for wet lab",
        "compatible " + "host",
        "experimentally " + "confirmed",
        "biological " + "suitability",
    ]
    for text in forbidden:
        assert text not in source


def test_project_quality_dashboard_review_context_summary_counts_existing_sections() -> None:
    from views.pathway_workspace_sections.project_quality_dashboard_section import (
        _dashboard_review_context_summary,
    )

    summary = _dashboard_review_context_summary(
        {
            "overall_documentation_status": "REVIEW_NEEDED",
            "metrics": {
                "pathway_steps_count": 2,
                "linked_artifacts_count": 1,
                "review_gap_count": 3,
            },
            "documentation_completeness": [{"label": "Steps"}, {"label": "Links"}],
            "review_guidance": ["Add missing review notes."],
            "boundary_notes": ["Documentation-only."],
        }
    )

    assert summary == {
        "status": "REVIEW_NEEDED",
        "pathway_steps": 2,
        "linked_artifacts": 1,
        "host_context_records": 0,
        "linked_promoter_profiles": 0,
        "review_gaps": 3,
        "checklist_items": 2,
        "guidance_items": 1,
        "boundary_notes": 1,
    }


def test_project_quality_dashboard_review_context_summary_defaults_missing_sections() -> None:
    from views.pathway_workspace_sections.project_quality_dashboard_section import (
        _dashboard_review_context_summary,
    )

    summary = _dashboard_review_context_summary(
        {
            "metrics": "not-a-dict",
            "documentation_completeness": None,
            "review_guidance": None,
            "next_actions": ["Review local documentation context."],
            "boundary_notes": "Documentation-only.",
        }
    )

    assert summary == {
        "status": "NOT_AVAILABLE",
        "pathway_steps": 0,
        "linked_artifacts": 0,
        "host_context_records": 0,
        "linked_promoter_profiles": 0,
        "review_gaps": 0,
        "checklist_items": 0,
        "guidance_items": 1,
        "boundary_notes": 0,
    }


def test_step2_component_context_manual_follow_up_summary_counts_review_context_only() -> None:
    from views.pathway_workspace_sections.project_quality_dashboard_section import (
        _step2_component_context_manual_follow_up_summary,
    )

    summary = _step2_component_context_manual_follow_up_summary(
        {
            "summary": {"total_rows": 2, "manual_follow_up_rows": 1},
            "rows": [
                {
                    "category": "host/context",
                    "step2_value": "E. coli",
                    "asset_label": "Host context note",
                    "source_provenance_review": "recorded context",
                    "record_review_status": "review noted",
                    "manual_follow_up": "Review source/provenance note.",
                },
                {
                    "category": "promoter",
                    "step2_value": "pTac",
                    "asset_label": "Promoter context note",
                    "source_provenance_review": "manual follow-up",
                    "record_review_status": "manual follow-up",
                    "manual_follow_up": "Record source/provenance review.",
                },
            ],
        }
    )

    assert summary == {
        "status": "AVAILABLE",
        "total_rows": 2,
        "source_provenance_review_rows": 2,
        "record_review_status_rows": 2,
        "manual_follow_up_rows": 1,
        "empty_state": "No current Step 2 Component Library context is available for this Dashboard summary.",
    }
    rendered_summary = str(summary).lower()
    for hidden_choice in ["e. coli", "ptac", "host/context", "promoter"]:
        assert hidden_choice not in rendered_summary


def test_step2_component_context_manual_follow_up_summary_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section._render_step2_component_context_manual_follow_up_summary(None)

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[call["label"] for call in fake_st.expander_calls],
        ]
    )
    assert "Step 2 Component Library context - manual follow-up summary" in rendered
    assert "current-session review context" in rendered
    assert "source/provenance review" in rendered
    assert "record review status" in rendered
    assert "manual follow-up" in rendered
    assert "not counted as a Dashboard gap" in rendered
    assert "not saved as evidence" in rendered
    assert "No current Step 2 Component Library context is available for this Dashboard summary." in rendered
    assert any(
        call["label"] == "Step 2 Component Library context - manual follow-up summary"
        and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    assert fake_st.metric_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_step2_component_context_manual_follow_up_summary_renders_without_component_choices(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section._render_step2_component_context_manual_follow_up_summary(
        {
            "summary": {"total_rows": 3, "manual_follow_up_rows": 2},
            "rows": [
                {
                    "category": "host/context",
                    "step2_value": "best " + "host",
                    "source_provenance_review": "manual follow-up",
                    "record_review_status": "manual follow-up",
                    "manual_follow_up": "Review source/provenance note.",
                },
                {
                    "category": "promoter",
                    "step2_value": "best " + "promoter",
                    "source_provenance_review": "recorded context",
                    "record_review_status": "review noted",
                    "manual_follow_up": "Review record status.",
                },
            ],
        }
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
        ]
    ).lower()
    assert "step 2 component library context - manual follow-up summary" in rendered
    assert "current-session review context: 3" in rendered
    assert "source/provenance review: 2" in rendered
    assert "record review status: 2" in rendered
    assert "manual follow-up: 2" in rendered
    assert "not counted as a dashboard gap" in rendered
    assert "not saved as evidence" in rendered
    for unsafe in [
        "best " + "host",
        "best " + "promoter",
        "optimized",
        "high-expression",
        "valid" + "ated",
        "wet-lab-ready",
        "score:",
        "severity:",
    ]:
        assert unsafe not in rendered
    assert fake_st.dataframes == []


def test_handoff_review_preview_passes_current_step2_context_to_report_and_handoff(monkeypatch) -> None:
    step2_context = {
        "rows": [{"category": "promoter", "asset_id": "handoff-promoter"}],
        "summary": {"total_rows": 1, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 0},
        "documentation_boundary_note": "Step 2 current-session documentation-only review context.",
    }
    captured_report: dict[str, object] = {}
    captured_handoff: dict[str, object] = {}
    report_appendix = {
        "status": "AVAILABLE",
        "rows": [{"Step 2 context category": "promoter"}],
        "summary": {"total_rows": 1, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 0},
        "total_rows_available": 1,
    }

    def _build_report(*_args, **kwargs):
        captured_report.update(kwargs)
        return {
            "candidate_evidence_human_review_queue": {},
            "plant_promoter_evidence_gap_review": {},
            "project_review_follow_up_index": {"summary": {"total_follow_up_items": 0}, "rows": []},
            "step2_component_context_appendix": report_appendix,
        }

    def _build_handoff(**kwargs):
        captured_handoff.update(kwargs)
        return {
            "summary": {"total_follow_up_items": 0},
            "checklist": [],
            "follow_up_rows": [],
            "step2_component_context_appendix": kwargs.get("step2_component_context_appendix"),
            "markdown": "## Project review handoff center\nStep 2 recorded Component Library context appendix",
        }

    monkeypatch.setattr(
        quality_dashboard_section,
        "current_step2_component_context_readback",
        lambda: step2_context,
    )
    monkeypatch.setattr(quality_dashboard_section, "build_project_review_report", _build_report)
    monkeypatch.setattr(quality_dashboard_section, "build_project_review_handoff_center", _build_handoff)
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {"summary": {}, "rows": []},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_host_chassis_context_summary",
        lambda project, linked_catalog_assets=None: {"rows": []},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_handoff_package_preview",
        lambda handoff, project_label="", **kwargs: {"title": "preview", "handoff": handoff},
    )

    handoff, handoff_preview = quality_dashboard_section._build_project_handoff_review_preview(
        project={"id": 244, "name": "R244 handoff"},
        steps=[],
        linked_tool_artifacts=[],
        linked_catalog_assets=[],
    )

    assert captured_report["step2_component_context"] is step2_context
    assert captured_handoff["step2_component_context_appendix"] is report_appendix
    assert handoff["step2_component_context_appendix"] is report_appendix
    assert handoff_preview["handoff"] is handoff


def test_handoff_review_preview_missing_step2_context_uses_empty_appendix(monkeypatch) -> None:
    captured_report: dict[str, object] = {}
    captured_handoff: dict[str, object] = {}

    def _build_report(*args, **kwargs):
        captured_report.update(kwargs)
        return {
            **quality_dashboard_section.normalize_generated_output_claims({}),
            **_minimal_report_with_step2_appendix(args, kwargs),
        }

    def _build_handoff(**kwargs):
        captured_handoff.update(kwargs)
        return {
            "summary": {"total_follow_up_items": 0},
            "checklist": [],
            "follow_up_rows": [],
            "step2_component_context_appendix": kwargs.get("step2_component_context_appendix"),
            "markdown": "## Project review handoff center",
        }

    monkeypatch.setattr(
        quality_dashboard_section,
        "current_step2_component_context_readback",
        lambda: None,
    )
    monkeypatch.setattr(quality_dashboard_section, "build_project_review_report", _build_report)
    monkeypatch.setattr(quality_dashboard_section, "build_project_review_handoff_center", _build_handoff)
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {"summary": {}, "rows": []},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_host_chassis_context_summary",
        lambda project, linked_catalog_assets=None: {"rows": []},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_handoff_package_preview",
        lambda handoff, project_label="", **kwargs: {"title": "preview"},
    )

    quality_dashboard_section._build_project_handoff_review_preview(
        project={"id": 245, "name": "R244 empty handoff"},
        steps=[],
        linked_tool_artifacts=[],
        linked_catalog_assets=[],
    )

    assert captured_report["step2_component_context"] is None
    assert captured_handoff["step2_component_context_appendix"]["status"] == "NOT_AVAILABLE"
    assert captured_handoff["step2_component_context_appendix"]["rows"] == []
    assert captured_handoff["step2_component_context_appendix"]["empty_state_message"] == (
        "No current Step 2 Component Library context is available for this review appendix."
    )


def test_dashboard_direct_handoff_receives_report_step2_appendix_without_new_gap_or_codon_link(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    report_appendix = {
        "status": "AVAILABLE",
        "rows": [{"Step 2 context category": "promoter"}],
        "summary": {"total_rows": 1, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 1},
        "total_rows_available": 1,
    }
    captured_handoff: dict[str, object] = {}

    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_quality_dashboard",
        lambda *args, **kwargs: {
            "overall_documentation_status": "AVAILABLE",
            "metrics": {"pathway_steps_count": 0, "linked_artifacts_count": 0, "review_gap_count": 0},
            "documentation_completeness": [],
            "review_guidance": [],
            "boundary_notes": [],
            "host_chassis_context_status": {"rows": []},
            "linked_catalog_assets_status": {},
            "saved_design_snapshot_status": {"status": "NOT_AVAILABLE"},
            "export_package_status": {"status": "NOT_AVAILABLE"},
            "import_safety_status": {"status": "NOT_AVAILABLE"},
            "package_exchange_review_trail": {},
            "review_gaps": [],
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "current_step2_component_context_readback",
        lambda: {"rows": [{"category": "promoter", "asset_id": "dashboard-promoter"}]},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_review_report",
        lambda *args, **kwargs: {
            "candidate_evidence_human_review_queue": {},
            "plant_promoter_evidence_gap_review": {},
            "project_review_follow_up_index": {"summary": {"total_follow_up_items": 0}, "rows": []},
            "step2_component_context_appendix": report_appendix,
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {"summary": {}, "rows": [], "boundary_notes": []},
    )

    def _build_handoff(**kwargs):
        captured_handoff.update(kwargs)
        return {
            "summary": {
                "total_follow_up_items": 0,
                "expression_construct_documentation_follow_up_count": 0,
                "candidate_evidence_follow_up_count": 0,
                "promoter_source_review_follow_up_count": 0,
                "host_context_documentation_follow_up_count": 0,
            },
            "checklist": [],
            "follow_up_rows": [],
            "step2_component_context_appendix": kwargs.get("step2_component_context_appendix"),
            "markdown": "## Project review handoff center",
        }

    monkeypatch.setattr(quality_dashboard_section, "build_project_review_handoff_center", _build_handoff)
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_handoff_package_preview",
        lambda handoff, project_label="", **kwargs: {
            "title": "Project handoff package preview",
            "snapshot_review_card": {},
            "qr_verification_payload": {},
            "handoff_workspace_summary": {},
            "handoff_workspace_nav_rows": [],
            "included_documentation_preview": [],
            "traceability_matrix_summary": {},
            "traceability_matrix_rows": [],
            "review_sheet_sections": [],
            "markdown": "",
            "review_sheet_markdown": "",
            "review_sheet_plain_text": "",
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_validation_case_package",
        lambda **kwargs: {
            "summary": {},
            "identity_payload": {},
            "markdown": "## Validation Case Package",
            "plain_text": "Validation Case Package",
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "render_documentation_consistency_provenance_panel",
        lambda *args, **kwargs: None,
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 246, "name": "R244 dashboard"},
        steps=[],
        linked_catalog_assets=[],
    )

    assert captured_handoff["step2_component_context_appendix"] is report_appendix
    assert fake_st.session_state == {}
    assert "step2_component_context" not in str(captured_handoff.get("follow_up_index", {})).lower()
    assert "codon" not in captured_handoff
    assert fake_st.download_button_calls == []


def test_project_quality_dashboard_renders_current_session_step2_manual_summary_without_gap_changes(
    monkeypatch,
) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    step2_context = {
        "summary": {"total_rows": 2, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 1},
        "rows": [
            {
                "category": "host/context",
                "step2_value": "best " + "host",
                "asset_label": "Host context note",
                "source_provenance_review": "recorded context",
                "record_review_status": "record review noted",
                "manual_follow_up": "Review source/provenance note before citing context.",
            },
            {
                "category": "promoter",
                "step2_value": "best " + "promoter",
                "asset_label": "Promoter context note",
                "source_provenance_review": "manual follow-up",
                "record_review_status": "manual follow-up",
                "manual_follow_up": "Record source/provenance review.",
            },
        ],
    }
    captured_dashboard: dict[str, object] = {}
    captured_report: dict[str, object] = {}
    report_appendix = {
        "status": "AVAILABLE",
        "rows": [{"Step 2 context category": "promoter"}],
        "summary": {"total_rows": 2, "rows_with_recorded_assets": 1, "manual_follow_up_rows": 1},
        "total_rows_available": 2,
    }

    def _build_dashboard(*args, **kwargs):
        dashboard = {
            "overall_documentation_status": "NEEDS_REVIEW",
            "metrics": {
                "pathway_steps_count": 1,
                "linked_artifacts_count": 0,
                "review_gap_count": 3,
            },
            "documentation_completeness": [],
            "review_guidance": [],
            "boundary_notes": [],
            "host_chassis_context_status": {"rows": []},
            "linked_catalog_assets_status": {},
            "saved_design_snapshot_status": {"status": "NOT_AVAILABLE"},
            "export_package_status": {"status": "NOT_AVAILABLE"},
            "import_safety_status": {"status": "NOT_AVAILABLE"},
            "package_exchange_review_trail": {},
            "review_gaps": [{"gap_id": "no_linked_documentation_artifacts"}],
        }
        captured_dashboard.update(dashboard)
        return dashboard

    monkeypatch.setattr(quality_dashboard_section, "build_project_quality_dashboard", _build_dashboard)
    monkeypatch.setattr(quality_dashboard_section, "current_step2_component_context_readback", lambda: step2_context)

    def _build_report(*_args, **kwargs):
        captured_report.update(kwargs)
        return {
            "candidate_evidence_human_review_queue": {},
            "plant_promoter_evidence_gap_review": {},
            "project_review_follow_up_index": {"summary": {"total_follow_up_items": 0}, "rows": []},
            "step2_component_context_appendix": report_appendix,
        }

    monkeypatch.setattr(quality_dashboard_section, "build_project_review_report", _build_report)
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {"summary": {}, "rows": [], "boundary_notes": []},
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_review_handoff_center",
        lambda **kwargs: {
            "summary": {"total_follow_up_items": 0},
            "checklist": [],
            "follow_up_rows": [],
            "step2_component_context_appendix": kwargs.get("step2_component_context_appendix"),
            "markdown": "## Project review handoff center",
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_handoff_package_preview",
        lambda handoff, project_label="", **kwargs: {
            "title": "Project handoff package preview",
            "snapshot_review_card": {},
            "qr_verification_payload": {},
            "handoff_workspace_summary": {},
            "handoff_workspace_nav_rows": [],
            "included_documentation_preview": [],
            "traceability_matrix_summary": {},
            "traceability_matrix_rows": [],
            "review_sheet_sections": [],
            "markdown": "",
            "review_sheet_markdown": "",
            "review_sheet_plain_text": "",
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_validation_case_package",
        lambda **kwargs: {
            "summary": {},
            "identity_payload": {},
            "markdown": "## Validation Case Package",
            "plain_text": "Validation Case Package",
        },
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "render_documentation_consistency_provenance_panel",
        lambda *args, **kwargs: None,
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 247, "name": "R247 Dashboard"},
        steps=[{"step_name": "Documentation step"}],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[str(rows) for rows in fake_st.dataframes],
        ]
    ).lower()
    assert "step 2 component library context - manual follow-up summary" in rendered
    assert "current-session review context: 2" in rendered
    assert "source/provenance review: 2" in rendered
    assert "record review status: 2" in rendered
    assert "manual follow-up: 1" in rendered
    assert "not counted as a dashboard gap" in rendered
    assert "not saved as evidence" in rendered
    assert captured_report["step2_component_context"] is step2_context
    assert captured_dashboard["metrics"]["review_gap_count"] == 3
    assert {gap["gap_id"] for gap in captured_dashboard["review_gaps"]} == {
        "no_linked_documentation_artifacts"
    }
    assert "step2_component_context_gap" not in rendered
    for unsafe in [
        "best " + "host",
        "best " + "promoter",
        "optimized",
        "high-expression",
        "valid" + "ated",
        "wet-lab-ready",
        "risk score",
        "readiness score",
    ]:
        assert unsafe not in rendered
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_r244_source_does_not_add_dashboard_gap_type_or_codon_linkage() -> None:
    source = "\n".join(
        line
        for line in SECTION.read_text(encoding="utf-8").splitlines()
        if "step2_component" in line.lower() or "codon_step3" in line.lower()
    ).lower()

    assert "step2_component_context_gap" not in source
    assert "codon usage preview" not in source
    assert "codon_step3" not in source


def _minimal_report_with_step2_appendix(args, kwargs) -> dict[str, object]:
    from services.project_review_report_service import build_project_review_report

    report = build_project_review_report(*args, **kwargs)
    return {
        "candidate_evidence_human_review_queue": report["candidate_evidence_human_review_queue"],
        "plant_promoter_evidence_gap_review": report["plant_promoter_evidence_gap_review"],
        "project_review_follow_up_index": report["project_review_follow_up_index"],
        "step2_component_context_appendix": report["step2_component_context_appendix"],
    }


def test_candidate_evidence_review_matrix_panel_renders_summary_and_table(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel(
        [
            {
                "asset_id": "plant-promoter-101",
                "asset_display_name": "Maize promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-101",
                },
                "review_status_snapshot": {
                    "review_status": "source review recorded",
                },
                "asset_snapshot": {
                    "snapshot_hash": "sha256:abc123",
                },
            },
            {
                "asset_id": "plant-promoter-202",
                "asset_display_name": "Partial promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {},
                "review_status_snapshot": {},
                "asset_snapshot": {},
            },
        ]
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )
    assert "Candidate Evidence Review Matrix" in rendered
    assert "Documentation-only source/provenance and record review status check." in rendered
    assert "This matrix supports manual documentation review planning only" in rendered
    assert any(call["label"] == "evidence review records" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "record review complete" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "record review gaps" and call["value"] == "1" for call in fake_st.metric_calls)
    assert fake_st.info_messages == []

    queue_rows = fake_st.dataframes[0]
    assert queue_rows[0]["Queue item id"]
    assert queue_rows[0]["Candidate label"]
    assert queue_rows[0]["Category"]
    assert queue_rows[0]["Severity"]
    assert queue_rows[0]["Issue"]
    assert queue_rows[0]["Human follow-up"]
    assert queue_rows[0]["Source context"]

    table_rows = fake_st.dataframes[1]
    assert table_rows[0]["Candidate label"] == "Maize promoter source context"
    assert table_rows[0]["Record review status"] == "documentation-complete"
    assert table_rows[0]["Review focus"] == "manual follow-up review"
    assert table_rows[0]["Missing fields"] == ""
    assert table_rows[0]["Next documentation review action"]
    assert table_rows[1]["Candidate label"] == "Partial promoter source context"
    assert "source_hash" in table_rows[1]["Missing fields"]
    assert table_rows[1]["Review focus"] == "source/provenance and record review"
    assert "Next documentation review action" in table_rows[1]
    assert fake_st.expander_calls == [
        {"label": "Review Snapshot", "expanded": False},
        {"label": "Human Review Queue", "expanded": False},
    ]
    assert len(fake_st.code_calls) == 1
    assert fake_st.code_calls[0]["language"] == "markdown"
    assert "# Candidate Evidence Review Snapshot" in fake_st.code_calls[0]["body"]
    assert "- candidate records: 2" in fake_st.code_calls[0]["body"]
    assert any("mentor/demo walkthroughs" in message for message in fake_st.caption_messages)
    assert any("not a candidate decision or biological proof record" in message for message in fake_st.caption_messages)
    assert any(call["label"] == "queue items" and call["value"] == "4" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/provenance gaps" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "metadata needs review" and call["value"] == "0" for call in fake_st.metric_calls)
    assert any(call["label"] == "manual follow-up" and call["value"] == "2" for call in fake_st.metric_calls)


def test_candidate_evidence_review_matrix_panel_field_legend_renders_safe_labels(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel(
        [
            {
                "asset_id": "plant-promoter-101",
                "asset_display_name": "Maize promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-101",
                },
                "review_status_snapshot": {
                    "review_status": "source review recorded",
                },
                "asset_snapshot": {
                    "snapshot_hash": "sha256:abc123",
                },
            }
        ]
    )

    rendered = "\n".join(fake_st.caption_messages)
    expected_legend_labels = [
        "Field legend:",
        "candidate_label",
        "source_category",
        "source_identifier",
        "provenance_status",
        "record_review_status",
        "review_focus",
        "review_status",
        "missing_fields",
        "next_manual_action",
        "boundary_note",
    ]
    for label in expected_legend_labels:
        assert label in rendered
    assert "manual documentation review note for follow-up" in rendered
    assert "documentation-only boundary for this matrix row" in rendered


def test_candidate_evidence_review_matrix_panel_empty_state_is_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel([])

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages).lower()
    assert "documentation-only" in rendered
    assert "no candidate evidence records are currently available for review" in rendered
    assert "documentation review planning" in rendered
    assert "documentation gap cue" in rendered
    assert "read-only matrix" in rendered
    assert "project review report follow-up surfaces" in rendered
    assert "no human review follow-up items are currently queued" in rendered
    assert any(call["label"] == "evidence review records" and call["value"] == "0" for call in fake_st.metric_calls)
    assert fake_st.dataframes == []
    assert len(fake_st.code_calls) == 1
    assert "## Empty state" in fake_st.code_calls[0]["body"]


def test_candidate_evidence_review_matrix_panel_copy_avoids_r102_forbidden_wording(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel([])

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.code_calls],
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    ).lower()
    for term in R102_FORBIDDEN_CANDIDATE_MATRIX_TERMS:
        assert term not in rendered


def test_candidate_evidence_review_matrix_panel_stays_read_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel([])

    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []
    assert len(fake_st.code_calls) == 1


def test_candidate_evidence_review_matrix_panel_human_review_queue_is_read_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section.render_candidate_evidence_review_matrix_panel(
        [
            {
                "asset_id": "plant-promoter-202",
                "asset_display_name": "Partial promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {},
                "review_status_snapshot": {},
                "asset_snapshot": {},
            },
        ]
    )

    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []
    assert any(call["label"] == "Human Review Queue" for call in fake_st.expander_calls)


def test_project_quality_dashboard_renders_follow_up_index_summary(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 51, "name": "Dashboard follow-up index"},
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "plant-promoter-202",
                "asset_display_name": "Partial promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {},
                "review_status_snapshot": {},
                "asset_snapshot": {},
            },
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
        ]
    )

    assert "Project Review Follow-up Index" in rendered
    assert "Collapsed read-only follow-up summary for manual documentation triage across project review queues." in rendered
    assert any(call["label"] == "Project Review Follow-up Index" for call in fake_st.expander_calls)
    assert any(call["label"] == "total follow-up items" for call in fake_st.metric_calls)


def test_project_quality_dashboard_renders_generic_component_library_asset_readback(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 204, "name": "Generic asset readback dashboard"},
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "plant-promoter-r204",
                "asset_display_name": "R204 promoter source context",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-r204",
                    "reference_origin": "Pathway Workspace linked catalog assets",
                },
                "asset_snapshot": {
                    "asset_label": "R204 promoter source context",
                    "species": "Nicotiana benthamiana",
                    "tissue_contexts": ["leaf"],
                },
                "review_status_snapshot": {"review_status": "human review needed"},
            },
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
        ]
    )

    assert "Generic Component Library asset readback" in rendered
    assert "Read-only generic Component Library asset readback" in rendered
    assert "This section reuses the Component Library presenter" in rendered
    assert "does not create a universal asset database model" in rendered
    assert "Documentation-only Component Library asset readback" in rendered
    assert any(call["label"] == "asset readback rows" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "asset type groups" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/provenance rows" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "record review rows" and call["value"] == "1" for call in fake_st.metric_calls)
    readback_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Asset label" in rows[0]
        ),
        [],
    )
    assert readback_rows
    assert readback_rows[0]["Asset label"] == "R204 promoter source context"
    assert readback_rows[0]["Asset type"] == "promoter"
    assert "Plant Promoter Catalog" in readback_rows[0]["Source/provenance identity"]
    assert readback_rows[0]["Documentation context note"] == (
        "Documentation context: Documentation context not provided; "
        "origin: Pathway Workspace linked catalog assets; role: Not recorded; "
        "link state: Linked catalog reference. "
        "Source/provenance identity remains Plant Promoter Catalog / plant-promoter-r204."
    )
    assert "Documentation-only Component Library asset readback" in readback_rows[0]["Documentation boundary note"]
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_project_quality_dashboard_reuses_component_library_readback_presenter(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    observed: dict[str, object] = {}
    source_assets = [
        {
            "asset_id": "r204-gene-context",
            "asset_display_name": "R204 gene source context",
            "asset_type": "cds_target",
        }
    ]

    def _fake_presenter(*, linked_catalog_assets=None, **kwargs):
        observed["linked_catalog_assets"] = linked_catalog_assets
        observed["kwargs"] = kwargs
        return {
            "summary": {
                "total_asset_rows": 1,
                "asset_type_count": 1,
                "rows_with_source_provenance_identity": 1,
                "rows_with_evidence_review_metadata": 1,
            },
            "rows": [
                {
                    "Asset label": "Presenter supplied row",
                    "Asset type": "CDS / gene",
                    "Domain/chassis context": "Not recorded",
                    "Source/provenance identity": "Presenter source identity",
                    "Record review status": "Presenter review status",
                    "Documentation context note": "Presenter documentation context note.",
                    "Type-specific notes": "Presenter type note",
                    "Documentation boundary note": "Documentation-only presenter boundary.",
                }
            ],
            "columns": [
                "Asset label",
                "Asset type",
                "Domain/chassis context",
                "Source/provenance identity",
                "Record review status",
                "Documentation context note",
                "Type-specific notes",
                "Documentation boundary note",
            ],
            "empty_state": "No presenter rows.",
            "documentation_boundary_note": "Documentation-only presenter boundary.",
            "source_identity_note": "Presenter source identity note.",
        }

    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_component_library_asset_readback_presenter",
        _fake_presenter,
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 205, "name": "Presenter reuse dashboard"},
        steps=[],
        linked_catalog_assets=source_assets,
    )

    assert observed["linked_catalog_assets"] == source_assets
    assert observed["kwargs"] == {}
    readback_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and rows[0].get("Asset label") == "Presenter supplied row"
        ),
        [],
    )
    assert readback_rows
    assert readback_rows[0]["Source/provenance identity"] == "Presenter source identity"
    assert readback_rows[0]["Documentation context note"] == "Presenter documentation context note."
    assert any("Presenter source identity note." in message for message in fake_st.caption_messages)


def test_project_quality_dashboard_generic_asset_readback_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    quality_dashboard_section._render_generic_component_library_asset_readback_review([])

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages)
    assert "Read-only generic Component Library asset readback" in rendered
    assert "No Component Library source/provenance or record review status is available for generic readback." in rendered
    assert any(call["label"] == "asset readback rows" and call["value"] == "0" for call in fake_st.metric_calls)
    assert fake_st.dataframes == []
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_project_quality_dashboard_renders_expression_construct_follow_up_queue(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "status": "AVAILABLE",
            "section_title": "Expression construct documentation follow-up",
            "summary": {
                "total_component_rows": 3,
                "rows_with_source_reference_context": 2,
                "rows_needing_manual_follow_up": 2,
                "rows_missing_source_reference_context": 1,
                "rows_with_sequence_availability_note": 2,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 0,
                "rows_with_review_metadata_status": 3,
                "rows_with_review_note": 1,
            },
            "rows": [
                {
                    "Construct label": "Construct Alpha",
                    "Cassette label": "Cassette A",
                    "Component label": "Promoter A",
                    "Component category": "promoter",
                    "Issue type": "Missing source/reference context",
                    "Issue detail": "No source record or source note is recorded for this component row.",
                    "Manual follow-up note": "Add source/reference context for documentation review.",
                }
            ],
            "boundary_notes": [
                "Expression construct documentation follow-up is read-only project review context.",
                "It summarizes documented component rows and manual documentation gaps only.",
            ],
            "caption": (
                "Review full construct, cassette, component, source/reference, provenance, and review-note readback "
                "in Expression Constructs."
            ),
            "empty_state_message": "No Expression Construct component documentation follow-up items are currently visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 174, "name": "Construct follow-up dashboard"},
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

    assert "Expression construct documentation follow-up" in rendered
    assert "Read-only project-level queue for Expression Construct component documentation follow-up." in rendered
    assert "manual documentation gaps only" in rendered
    assert "Expression Constructs" in rendered
    assert any(
        call["label"] == "Expression construct documentation follow-up"
        for call in fake_st.expander_calls
    )
    assert any(call["label"] == "Component rows reviewed" and call["value"] == "3" for call in fake_st.metric_calls)
    assert any(call["label"] == "Source/reference context" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "Missing source/reference context" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "Documentation follow-up" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "Sequence availability note" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "Record review status" and call["value"] == "3" for call in fake_st.metric_calls)
    assert any(call["label"] == "Review note context" and call["value"] == "1" for call in fake_st.metric_calls)
    construct_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and rows[0].get("Construct label") == "Construct Alpha"
        ),
        [],
    )
    assert construct_rows[0] == {
        "Construct label": "Construct Alpha",
        "Cassette label": "Cassette A",
        "Component label": "Promoter A",
        "Component category": "promoter",
        "Issue type": "Missing source/reference context",
        "Issue detail": "No source record or source note is recorded for this component row.",
        "Manual follow-up note": "Add source/reference context for documentation review.",
    }
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_project_quality_dashboard_expression_construct_follow_up_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "status": "NOT_AVAILABLE",
            "summary": {
                "total_component_rows": 0,
                "rows_with_source_reference_context": 0,
                "rows_needing_manual_follow_up": 0,
                "rows_missing_source_reference_context": 0,
                "rows_with_sequence_availability_note": 0,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 0,
                "rows_with_review_metadata_status": 0,
                "rows_with_review_note": 0,
            },
            "rows": [],
            "boundary_notes": ["Expression construct documentation follow-up is read-only project review context."],
            "caption": "Review full component readback in Expression Constructs.",
            "empty_state_message": "No Expression Construct component documentation follow-up items are currently visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 175, "name": "Empty construct follow-up dashboard"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages)

    assert "Expression construct documentation follow-up is read-only project review context." in rendered
    assert "No Expression Construct component documentation follow-up items are currently visible." in rendered
    assert any(call["label"] == "Component rows reviewed" and call["value"] == "0" for call in fake_st.metric_calls)
    assert any(
        call["label"] == "Expression construct documentation follow-up"
        for call in fake_st.expander_calls
    )


def test_project_quality_dashboard_renders_handoff_center(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "summary": {
                "total_component_rows": 1,
                "rows_needing_manual_follow_up": 1,
                "rows_with_source_reference_context": 0,
                "rows_missing_source_reference_context": 1,
                "rows_with_sequence_availability_note": 0,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 0,
                "rows_with_review_metadata_status": 1,
                "rows_with_review_note": 0,
            },
            "rows": [
                {
                    "Construct label": "Construct A",
                    "Cassette label": "Cassette A",
                    "Component label": "Promoter A",
                    "Component category": "promoter",
                    "Issue type": "Missing source/reference context",
                    "Issue detail": "No source row recorded.",
                    "Manual follow-up note": "Add documentation source context.",
                }
            ],
            "boundary_notes": [],
            "caption": "Review full component readback in Expression Constructs.",
            "empty_state_message": "No Expression Construct component documentation follow-up items are visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 177, "name": "Handoff dashboard"},
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "plant-promoter-handoff",
                "asset_display_name": "Handoff promoter reference",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-handoff",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "asset_snapshot": {},
                "human_review_required": True,
            }
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )

    assert "Project review handoff center" in rendered
    assert "Read-only project-level handoff summary" in rendered
    assert "Handoff checklist" in rendered
    assert "Follow-up queue overview" in rendered
    assert "Component Library source/provenance readback" in rendered
    assert "Review Component Library records and missing source/provenance before handoff." in rendered
    assert "This section does not choose components or validate the design." in rendered
    assert "Read-only documentation review only." in rendered
    assert "Handoff promoter reference" in rendered
    assert "Promoter" in rendered
    assert "Source/provenance missing" in rendered
    assert "Manual follow-up needed" in rendered
    assert "Markdown handoff summary" in rendered
    assert "copy/review only" in rendered
    assert "## Project review handoff center" in rendered
    assert any(call["label"] == "total follow-up items" for call in fake_st.metric_calls)
    assert any(call["label"] == "expression construct follow-up" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "candidate evidence follow-up" for call in fake_st.metric_calls)
    assert any(call["label"] == "Component Library promoter asset source/review follow-up" for call in fake_st.metric_calls)
    assert any(call["label"] == "host/context follow-up" for call in fake_st.metric_calls)
    assert any(call["label"] == "Component Library slot rows" for call in fake_st.metric_calls)
    assert any(call["label"] == "slots with records" and call["value"] != "0" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/provenance follow-up slots" for call in fake_st.metric_calls)
    assert any(call["label"] == "manual follow-up slots" for call in fake_st.metric_calls)
    assert any(call["label"] == "Handoff checklist" for call in fake_st.expander_calls)
    assert any(call["label"] == "Follow-up queue overview" for call in fake_st.expander_calls)
    assert any(call["label"] == "Component Library source/provenance readback" for call in fake_st.expander_calls)
    assert any(call["label"] == "Markdown handoff summary" for call in fake_st.expander_calls)
    readback_rows = next(
        rows
        for rows in fake_st.dataframes
        if rows
            and isinstance(rows, list)
            and isinstance(rows[0], dict)
            and rows[0].get("Slot") == "Plant promoter context"
    )
    assert readback_rows[0]["Records"] == "Handoff promoter reference"
    assert "Source/provenance missing" in readback_rows[0]["Source/provenance status"]
    assert "Manual follow-up needed" in readback_rows[0]["Manual follow-up"]
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_project_review_handoff_center_component_library_readback_empty_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    handoff = quality_dashboard_section.build_project_review_handoff_center(
        expression_construct_queue={},
        candidate_queue={},
        promoter_queue={},
        host_chassis_context={"rows": [{"source_value": "E. coli documentation context"}]},
        component_library_records=[],
        report_markdown_available=False,
    )

    quality_dashboard_section._render_project_review_handoff_center(handoff)

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )

    assert "Component Library source/provenance readback" in rendered
    assert "No Component Library records are available for Handoff Review yet." in rendered
    assert "read-only source/provenance readback" in rendered
    assert any(call["label"] == "Component Library slot rows" and call["value"] == "0" for call in fake_st.metric_calls)
    assert any(call["label"] == "slots with records" and call["value"] == "0" for call in fake_st.metric_calls)
    assert not any(
        rows
        and isinstance(rows, list)
        and isinstance(rows[0], dict)
        and rows[0].get("Slot")
        for rows in fake_st.dataframes
    )
    for unsafe in [
        "automatic component recommendation",
        "optimized sequence",
        "best promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "validated construct",
        "cloning protocol",
        "wet-lab protocol",
        "yield prediction",
        "experimentally validated",
    ]:
        assert unsafe not in rendered.casefold()


def test_project_quality_dashboard_renders_handoff_package_preview(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "summary": {
                "total_component_rows": 1,
                "rows_needing_manual_follow_up": 1,
                "rows_with_source_reference_context": 0,
                "rows_missing_source_reference_context": 1,
                "rows_with_sequence_availability_note": 0,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 0,
                "rows_with_review_metadata_status": 1,
                "rows_with_review_note": 0,
            },
            "rows": [
                {
                    "Construct label": "Construct A",
                    "Cassette label": "Cassette A",
                    "Component label": "Promoter A",
                    "Component category": "promoter",
                    "Issue type": "Missing source/reference context",
                    "Issue detail": "No source row recorded.",
                    "Manual follow-up note": "Add documentation source context.",
                }
            ],
            "boundary_notes": [],
            "caption": "Review full component readback in Expression Constructs.",
            "empty_state_message": "No Expression Construct component documentation follow-up items are visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={
            "id": 178,
            "name": "Package preview dashboard",
            "target_gene": "crtI documentation target",
            "host": "E. coli BL21(DE3) documentation context",
            "vector_backbone": "pET backbone documentation context",
            "source_reference": "Manual sequence source note",
        },
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "plant-promoter-package-preview",
                "asset_display_name": "Package preview promoter reference",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-package-preview",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "asset_snapshot": {},
                "human_review_required": True,
            }
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )

    assert "Project handoff package preview" in rendered
    assert "Expression Vector Design Package preview" in rendered
    assert "Expression Vector Design Package Markdown preview" in rendered
    assert "Read-only Markdown preview for documentation review" in rendered
    assert "Documentation review only" in rendered
    assert "draft / needs review" in rendered
    assert "source/provenance" in rendered
    assert "Manual follow-up" in rendered
    assert "crtI documentation target" in rendered
    assert "E. coli BL21(DE3) documentation context" in rendered
    assert "pET backbone documentation context" in rendered
    assert "Manual sequence source note" in rendered
    for heading in [
        "## Package Identity",
        "## Target Gene / CDS / Protein",
        "## Host / Expression System",
        "## Expression Cassette Slot Review",
        "## Vector / Backbone",
        "## Sequence Basic Checks",
        "## Source / Provenance Summary",
        "## Gap / Manual Follow-up Review",
        "## Package Limitations",
    ]:
        assert heading in rendered
    assert "Project handoff review workspace" in rendered
    assert "bds-review-grid" in rendered
    assert "Handoff workspace metric details" in rendered
    assert "Full Handoff workspace review rows table" in rendered
    assert "Complete read-only detail table; long source, gap, and traceability values remain available here." in rendered
    assert "Read-only workspace for mentor, collaborator, platform, or internal project documentation review." in rendered
    assert "This workspace organizes local, read-only, documentation-only review surfaces for manual review." in rendered
    assert "No export package is created here. No file or download is created here." in rendered
    assert "Workspace Markdown map" in rendered
    assert "Workspace area" in rendered
    assert "Current status" in rendered
    assert "Key count or identity" in rendered
    assert "Review surface" in rendered
    assert "Where to inspect next" in rendered
    assert "Boundary note" in rendered
    assert "Handoff Center" in rendered
    assert "Package Preview" in rendered
    assert "Snapshot / MD5 / QR Payload" in rendered
    assert "Review Sheet Copy View" in rendered
    assert "Traceability Matrix" in rendered
    assert "Project Review Report Markdown" in rendered
    assert "Preview-only package preview" in rendered
    assert "Copy-only review sheet" in rendered
    assert "MD5/QR payload for preview matching only" in rendered
    assert "Read-only preview for human handoff review" in rendered
    assert "Package preview only; no export package is created here." in rendered
    assert "Handoff snapshot review card" in rendered
    assert "Snapshot metric details" in rendered
    assert "Read-only snapshot identity for preview review matching." in rendered
    assert "The MD5 code is for preview matching only, not a security signature or certification." in rendered
    assert "Handoff QR verification preview" in rendered
    assert "QR metric details" in rendered
    assert "Use this preview identity to match the same handoff snapshot during human review." in rendered
    assert "Payload-only fallback is used because the default dependency manifest does not include a QR rendering library." in rendered
    assert "Read-only QR verification payload for matching the same preview identity during human review." in rendered
    assert "QR verification payload" in rendered
    assert "BioDesign Studio handoff QR verification payload" in rendered
    assert "No file or download is created here." in rendered
    assert "Snapshot ID: md5:" in rendered
    assert "Handoff cover summary" in rendered
    assert "Included documentation preview" in rendered
    assert "Handoff checklist" in rendered
    assert "Manual follow-up queue" in rendered
    assert "Project handoff traceability matrix" in rendered
    assert "Traceability metric details are shown below for continuity with prior review checks." in rendered
    assert "Read-only traceability matrix linking each documentation source" in rendered
    assert "Included in review sheet" in rendered
    assert "Review next" in rendered
    assert "### Project handoff traceability matrix" in rendered
    assert "Markdown handoff preview" in rendered
    assert "Project handoff review sheet" in rendered
    assert "Read-only review sheet copy view for documentation handoff review." in rendered
    assert "Copy view only; no export package is created here and no file is generated here." in rendered
    assert "Markdown copy view" in rendered
    assert "Plain-text copy view" in rendered
    assert "## Project handoff review sheet" in rendered
    assert "### Snapshot review card" in rendered
    assert "### Handoff summary" in rendered
    assert "### Manual follow-up queue" in rendered
    assert "Project handoff review sheet" in rendered
    assert "Snapshot review card" in rendered
    assert "Handoff summary" in rendered
    assert "Manual follow-up queue" in rendered
    assert "Review-only documentation handoff review; not a downstream-use assessment." in rendered
    assert "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment" in rendered
    assert "## Project handoff package preview" in rendered
    assert "### Handoff snapshot review card" in rendered
    assert "Checksum algorithm: MD5" in rendered
    assert "No export package is created here." in rendered
    assert "No file is generated here." in rendered
    assert any(call["label"] == "project label" and call["value"] == "Package preview dashboard" for call in fake_st.metric_calls)
    assert any(call["label"] == "snapshot title" and call["value"] == "Project handoff package preview" for call in fake_st.metric_calls)
    assert any(call["label"] == "preview checksum" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "checksum algorithm" and call["value"] == "MD5" for call in fake_st.metric_calls)
    assert any(call["label"] == "QR checksum algorithm" and call["value"] == "MD5" for call in fake_st.metric_calls)
    assert any(call["label"] == "QR MD5 preview checksum" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "QR included surfaces" and call["value"] == "5" for call in fake_st.metric_calls)
    assert any(call["label"] == "QR manual follow-up" for call in fake_st.metric_calls)
    assert any(call["label"] == "included surfaces" and call["value"] == "5" for call in fake_st.metric_calls)
    assert any(call["label"] == "preview sections" for call in fake_st.metric_calls)
    assert any(call["label"] == "content length" for call in fake_st.metric_calls)
    assert any(call["label"] == "manual follow-up items" for call in fake_st.metric_calls)
    assert any(call["label"] == "documentation surfaces included" and call["value"] == "5" for call in fake_st.metric_calls)
    assert any(call["label"] == "workspace areas" and call["value"] == "6" for call in fake_st.metric_calls)
    assert any(call["label"] == "sections listed" and call["value"] == "7" for call in fake_st.metric_calls)
    assert any(call["label"] == "available sections" for call in fake_st.metric_calls)
    assert any(call["label"] == "overview status" and call["value"] == "AVAILABLE" for call in fake_st.metric_calls)
    assert any(call["label"] == "documentation surfaces" and call["value"] == "5" for call in fake_st.metric_calls)
    assert any(call["label"] == "traceability rows" for call in fake_st.metric_calls)
    assert any(call["label"] == "workspace snapshot checksum" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "QR payload status" and call["value"] == "AVAILABLE" for call in fake_st.metric_calls)
    assert any(call["label"] == "Workspace Markdown map" for call in fake_st.expander_calls)
    assert any(call["label"] == "Handoff workspace metric details" for call in fake_st.expander_calls)
    assert any(call["label"] == "Full Handoff workspace review rows table" for call in fake_st.expander_calls)
    assert any(call["label"] == "Output sections overview" for call in fake_st.expander_calls)
    assert any(call["label"] == "Snapshot metric details" for call in fake_st.expander_calls)
    assert any(call["label"] == "QR metric details" for call in fake_st.expander_calls)
    assert any(call["label"] == "Snapshot included surfaces" for call in fake_st.expander_calls)
    assert any(call["label"] == "QR verification payload" for call in fake_st.expander_calls)
    assert any(call["label"] == "Handoff cover summary" for call in fake_st.expander_calls)
    assert any(call["label"] == "Package preview metric details" for call in fake_st.expander_calls)
    assert any(call["label"] == "Included documentation preview" for call in fake_st.expander_calls)
    assert any(call["label"] == "Manual follow-up queue" for call in fake_st.expander_calls)
    assert any(call["label"] == "Project handoff traceability matrix" for call in fake_st.expander_calls)
    assert any(call["label"] == "Review sheet sections" for call in fake_st.expander_calls)
    assert any(call["label"] == "Markdown copy view" for call in fake_st.expander_calls)
    assert any(call["label"] == "Plain-text copy view" for call in fake_st.expander_calls)
    assert any(call["label"] == "matrix rows" for call in fake_st.metric_calls)
    assert any(call["label"] == "included in review sheet" for call in fake_st.metric_calls)
    assert any(call["label"] == "source/reference follow-up" for call in fake_st.metric_calls)
    assert any(call["label"] == "provenance/review follow-up" for call in fake_st.metric_calls)
    assert any(call["language"] == "markdown" and "## Project handoff review sheet" in call["body"] for call in fake_st.code_calls)
    assert any(call["language"] == "markdown" and "## Project handoff review workspace" in call["body"] for call in fake_st.code_calls)
    assert any(
        call["language"] == "markdown" and "## Package Identity" in call["body"] and "| MD5 |" in call["body"]
        for call in fake_st.code_calls
    )
    assert any(call["label"] == "EV package status" and call["value"] == "draft / needs review" for call in fake_st.metric_calls)
    assert any(call["label"] == "EV package MD5" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "Expression Vector Design Package Markdown preview" for call in fake_st.expander_calls)
    assert any(
        call["label"] == "Expression Vector Design Package Markdown preview" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    for unsafe in [
        "generated vector",
        "optimized design",
        "recommended promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "validated construct",
        "cloning protocol",
        "yield prediction",
        "experimentally validated",
    ]:
        assert unsafe not in rendered.casefold()
    assert any(call["language"] == "text" and "Project handoff review sheet" in call["body"] for call in fake_st.code_calls)
    assert any(call["language"] == "text" and "BioDesign Studio handoff QR verification payload" in call["body"] for call in fake_st.code_calls)
    preview_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Documentation surface" in rows[0]
        ),
        [],
    )
    assert preview_rows
    assert preview_rows[0]["Documentation surface"] == "construct/component documentation summary"
    workspace_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Workspace area" in rows[0]
        ),
        [],
    )
    assert workspace_rows
    assert [row["Workspace area"] for row in workspace_rows] == [
        "Handoff Center",
        "Package Preview",
        "Snapshot / MD5 / QR Payload",
        "Review Sheet Copy View",
        "Traceability Matrix",
        "Project Review Report Markdown",
    ]
    assert workspace_rows[2]["Key count or identity"].startswith("MD5 ")
    assert "Where to inspect next" in workspace_rows[0]
    assert "Boundary note" in workspace_rows[0]
    review_sheet_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Review sheet section" in rows[0]
        ),
        [],
    )
    assert review_sheet_rows
    assert review_sheet_rows[0]["Review sheet section"] == "Snapshot review card"
    traceability_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Included in review sheet" in rows[0]
        ),
        [],
    )
    assert traceability_rows
    assert traceability_rows[0]["Source surface"] == "Expression Constructs"
    assert "Review next" in traceability_rows[0]
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_handoff_review_workspace_section_is_first_class_read_only(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "_build_project_handoff_review_preview",
        lambda project, steps, linked_tool_artifacts, linked_catalog_assets: (
            {"title": "Project review handoff center"},
            {"title": "Project handoff package preview"},
        ),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_handoff_review_workspace",
        lambda preview: fake_st.caption("workspace renderer called"),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_review_handoff_center",
        lambda handoff: fake_st.caption("handoff center renderer called"),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_handoff_package_preview",
        lambda preview: fake_st.caption("package preview renderer called"),
    )

    quality_dashboard_section.render_project_handoff_review_workspace_section(
        project={
            "id": 185,
            "name": "First-class handoff workspace",
            "target_gene": "crtI documentation target",
            "host": "E. coli BL21(DE3) documentation context",
            "vector_backbone": "pET backbone documentation context",
            "source_reference": "Manual source/provenance note",
        },
        steps=[{"name": "Sequence source review"}],
        linked_catalog_assets=[
            {
                "asset_id": "handoff-package-preview-promoter",
                "asset_display_name": "Handoff preview promoter reference",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Component Library",
                    "profile_id": "handoff-package-preview-promoter",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "asset_snapshot": {},
                "human_review_required": True,
            }
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.subheaders,
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )
    assert "Handoff Review" in rendered
    assert "First-class read-only workspace for project handoff review surfaces" in rendered
    assert "does not export, download, create files, save records, package data" in rendered
    assert "workspace renderer called" in rendered
    assert "handoff center renderer called" in rendered
    assert "package preview renderer called" in rendered
    assert "Single-gene sample walkthrough helper" in rendered
    assert "Learning aid only for one gene / one protein / one enzyme expression-vector preparation." in rendered
    assert "Single-gene sample walkthrough readback" in rendered
    assert "Start here:" in rendered
    assert "What has been recorded:" in rendered
    assert "Source/provenance gaps:" in rendered
    assert "Manual follow-up:" in rendered
    assert "sample-enzyme-1 single-gene target record" in rendered
    assert "Target sequence source/provenance is not recorded." in rendered
    assert "The sample is read-only and in-memory only." in rendered
    assert any(call["label"] == "sample status" and call["value"] == "sample / needs review" for call in fake_st.metric_calls)
    assert any(call["label"] == "sample MD5" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "sample slot rows" for call in fake_st.metric_calls)
    assert any(call["label"] == "sample follow-up rows" for call in fake_st.metric_calls)
    assert "Expression Vector Design Package review preview" in rendered
    assert "Current record preview" in rendered
    assert "Expression Vector Design Package preview" in rendered
    assert "Expression Vector Design Package Markdown preview" in rendered
    assert "Read-only documentation-review preview" in rendered
    assert "Documentation review only" in rendered
    assert "Current-record source readback" in rendered
    assert "draft / needs review" in rendered
    assert "Expression Vector Design Package status: draft / needs review" in rendered
    assert any(
        call["label"] == "Expression Vector Design Package MD5" and len(call["value"]) == 32
        for call in fake_st.metric_calls
    )
    assert "source/provenance" in rendered
    assert "Manual follow-up" in rendered
    assert "crtI documentation target" in rendered
    assert "E. coli BL21(DE3) documentation context" in rendered
    assert "pET backbone documentation context" in rendered
    assert "Manual source/provenance note" in rendered
    assert "## Package Identity" in rendered
    assert "| MD5 |" in rendered
    assert "## Source / Provenance Summary" in rendered
    assert "## Gap / Manual Follow-up Review" in rendered
    source_readback_table = next(
        rows
        for rows in fake_st.dataframes
        if rows
        and isinstance(rows, list)
        and isinstance(rows[0], dict)
        and rows[0].get("Preview field") == "Target Gene / CDS / Protein"
    )
    assert [row["Preview field"] for row in source_readback_table] == [
        "Target Gene / CDS / Protein",
        "Expression Host",
        "Promoter",
        "CDS / Insert",
        "Vector / Backbone",
        "Sequence Basic Checks",
        "Manual Follow-up",
    ]
    assert source_readback_table[0]["Current value"] == "crtI documentation target"
    assert source_readback_table[0]["Source/readback origin"] == "current record"
    assert source_readback_table[1]["Current value"] == "E. coli BL21(DE3) documentation context"
    assert source_readback_table[2]["Preview field"] == "Promoter"
    assert source_readback_table[2]["Source/provenance status"] in {
        "source review needed",
        "needs source/provenance",
    }
    assert source_readback_table[-1]["Preview field"] == "Manual Follow-up"
    assert any(
        call["label"] == "Expression Vector Design Package Markdown preview" and call.get("expanded") is False
        for call in fake_st.expander_calls
    )
    for unsafe in [
        "generated vector",
        "optimized sequence",
        "recommended promoter",
        "best promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "validated construct",
        "cloning protocol",
        "wet-lab protocol",
        "yield prediction",
        "experimentally validated",
    ]:
        assert unsafe not in rendered.casefold()
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_handoff_review_expression_vector_preview_empty_state_keeps_sample_as_learning_aid(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "_build_project_handoff_review_preview",
        lambda project, steps, linked_tool_artifacts, linked_catalog_assets: (
            {"title": "Project review handoff center"},
            {"title": "Project handoff package preview"},
        ),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_handoff_review_workspace",
        lambda preview: fake_st.caption("workspace renderer called"),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_review_handoff_center",
        lambda handoff: fake_st.caption("handoff center renderer called"),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "_render_project_handoff_package_preview",
        lambda preview: fake_st.caption("package preview renderer called"),
    )
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_expression_construct_report_views",
        lambda project_id=None: [],
    )

    quality_dashboard_section.render_project_handoff_review_workspace_section(
        project={"id": 280, "name": "Only project container"},
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *fake_st.info_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
        ]
    )
    assert "Expression Vector Design Package review preview" in rendered
    assert "Current-record source readback" in rendered
    assert "No current expression vector record is available yet. Start from Expression Wizard or open a saved design." in rendered
    assert "Sample walkthrough remains available below as a learning aid only; it is not current project data." in rendered
    assert "Single-gene sample walkthrough helper (learning aid)" in rendered
    assert "sample-enzyme-1 single-gene target record" in rendered
    assert "Expression Vector Design Package Markdown preview" not in [
        call["label"] for call in fake_st.expander_calls
    ]
    source_readback_table = next(
        rows
        for rows in fake_st.dataframes
        if rows
        and isinstance(rows, list)
        and isinstance(rows[0], dict)
        and rows[0].get("Preview field") == "Target Gene / CDS / Protein"
    )
    assert len(source_readback_table) == 7
    assert {row["Source/readback origin"] for row in source_readback_table} == {"missing"}
    assert source_readback_table[0]["Current value"] == "Missing"
    assert "Start from Expression Wizard" in source_readback_table[0]["Follow-up"]
    assert "Current record preview" not in rendered
    assert fake_st.download_button_calls == []


def test_project_quality_dashboard_renders_validation_case_package(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "summary": {
                "total_component_rows": 1,
                "rows_needing_manual_follow_up": 1,
                "rows_with_source_reference_context": 1,
                "rows_missing_source_reference_context": 0,
                "rows_with_sequence_availability_note": 1,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 1,
                "rows_with_review_metadata_status": 1,
                "rows_with_review_note": 0,
            },
            "rows": [
                {
                    "Construct label": "Validation case construct",
                    "Cassette label": "Validation cassette",
                    "Component label": "CDS component",
                    "Component category": "coding sequence",
                    "Issue type": "Needs conservation check",
                    "Issue detail": "Conservation evidence needs documentation review.",
                    "Manual follow-up note": "Manual documentation follow-up: add conservation review note.",
                }
            ],
            "boundary_notes": [],
            "caption": "Review full component readback in Expression Constructs.",
            "empty_state_message": "No Expression Construct component documentation follow-up items are visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={
            "id": 222,
            "name": "R222 user-defined enzyme case",
            "description": "Teacher/company feasibility review case.",
            "candidate_expression_systems": [
                "bacterial documentation option",
                "yeast documentation option",
            ],
        },
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
            *[str(rows) for rows in fake_st.dataframes],
        ]
    )

    assert "Validation Case Package" in rendered
    assert "Documentation-only pre-experiment package for teacher/company feasibility review." in rendered
    assert "R222 user-defined enzyme case" in rendered
    assert "bacterial documentation option" in rendered
    assert "yeast documentation option" in rendered
    assert "Candidate target protein/product/pathway" in rendered
    assert "Construct design summary" in rendered
    assert "Component evidence/provenance summary" in rendered
    assert "Codon usage / optimization status summary" in rendered
    assert "Component conservation review summary" in rendered
    assert "Company feasibility feedback placeholder" in rendered
    assert "Experiment status placeholder" in rendered
    assert "Result summary placeholder" in rendered
    assert "BioDesign Studio validation case package identity payload" in rendered
    assert "It is not a wet-lab protocol." in rendered
    assert "It does not guarantee expression." in rendered
    assert "It does not forecast yield or experimental success." in rendered
    assert "It does not select a preferred expression system." in rendered
    assert "It does not replace expert/company review." in rendered
    assert "It does not perform codon rewriting or automatic conservation classification." in rendered
    assert any(call["label"] == "candidate systems" and call["value"] == "2" for call in fake_st.metric_calls)
    assert any(call["label"] == "component rows" and call["value"] == "1" for call in fake_st.metric_calls)
    assert any(call["label"] == "MD5 preview checksum" and len(call["value"]) == 32 for call in fake_st.metric_calls)
    assert any(call["label"] == "Validation case overview" for call in fake_st.expander_calls)
    assert any(call["label"] == "Validation case package identity" for call in fake_st.expander_calls)
    assert any(call["language"] == "markdown" and "## Validation Case Package" in call["body"] for call in fake_st.code_calls)
    assert fake_st.download_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []
    assert fake_st.checkbox_calls == []
    assert fake_st.selectbox_calls == []
    assert fake_st.form_submit_button_calls == []


def test_project_quality_dashboard_renders_host_chassis_context_summary(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 61, "name": "Host dashboard", "host": "E. coli BL21(DE3)"},
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "host-note-61",
                "asset_display_name": "Mammalian host context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {
                    "host_context": "CHO cell documentation context",
                },
            },
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[call["label"] for call in fake_st.expander_calls],
        ]
    )
    assert "Host / Chassis Context Summary" in rendered
    assert "chassis-neutral review context only" in rendered
    assert "Plant context is supported as one documentation example only" in rendered
    assert any(call["label"] == "Host / Chassis Context Summary" for call in fake_st.expander_calls)
    host_rows = next(
        (
            rows
            for rows in fake_st.dataframes
            if rows and isinstance(rows, list) and "Normalized context" in rows[0]
        ),
        [],
    )
    assert host_rows[0]["Normalized context"] == "Bacterial"
    assert host_rows[1]["Normalized context"] == "Mammalian"


def test_project_quality_dashboard_renders_with_upstream_host_compatibility_copy(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(
        quality_dashboard_section,
        "build_project_construct_component_review_queue",
        lambda project_id=None: {
            "summary": {
                "total_component_rows": 0,
                "rows_needing_manual_follow_up": 0,
                "rows_with_source_reference_context": 0,
                "rows_missing_source_reference_context": 0,
                "rows_with_sequence_availability_note": 0,
                "rows_with_conservation_review_context": 0,
                "rows_needing_conservation_follow_up": 0,
                "rows_with_review_metadata_status": 0,
                "rows_with_review_note": 0,
            },
            "rows": [],
            "boundary_notes": [],
            "caption": "Review full component readback in Expression Constructs.",
            "empty_state_message": "No Expression Construct component documentation follow-up items are visible.",
        },
    )

    quality_dashboard_section.render_project_quality_dashboard_section(
        project={"id": 186, "name": "Host wording dashboard", "host": "Host compatibility note"},
        steps=[],
        linked_catalog_assets=[
            {
                "asset_id": "host-note-186",
                "asset_display_name": "Host compatibility context note",
                "asset_type": "host_chassis_context_note",
                "documentation_note": "Compatible host upstream note",
                "source_context_snapshot": {
                    "host_context": "Host compatibility source note",
                    "project_documentation_context": "Compatibility proof readback",
                    "source_review_status": "Host readiness review pending",
                },
                "review_status_snapshot": {
                    "review_status": "Validated host review note",
                },
            },
            {
                "asset_id": "catalog-host-186",
                "asset_display_name": "Recommended host catalog row",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "design_record_context",
                "documentation_note": "Host compatibility catalog note",
                "source_context_snapshot": {
                    "catalog": "Local Design Asset Catalog",
                    "reference_origin": "Expression Wizard catalog context",
                    "source_labels": "Ready host source label",
                },
                "asset_snapshot": {
                    "asset_label": "Compatible host asset label",
                    "source_label": "Host compatibility source",
                    "documentation_status": "Recommended host review",
                },
                "review_status_snapshot": {"missing_metadata_count": 1},
            },
        ],
    )

    rendered = "\n".join(
        [
            *fake_st.caption_messages,
            *[str(call["body"]) for call in fake_st.markdown_calls],
            *[f"{call['label']}: {call['value']}" for call in fake_st.metric_calls],
            *[call["label"] for call in fake_st.expander_calls],
            *[call["body"] for call in fake_st.code_calls],
            *[str(rows) for rows in fake_st.dataframes],
        ]
    ).lower()

    assert "project quality dashboard" in rendered
    for unsafe in [
        "host compatibility",
        "compatible host",
        "compatibility proof",
        "host readiness",
        "ready host",
        "validated host",
        "recommended host",
    ]:
        assert unsafe not in rendered
    assert "host context documentation" in rendered
    assert fake_st.error_messages == []
