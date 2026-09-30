from __future__ import annotations

import copy
import inspect
import os
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_report_service import (
    OPTIONAL_SECTION_OMISSION_NOTICE,
    REVIEW_NOTES_BOUNDARY_STATEMENT,
    PathwayReportConfig,
    generate_pathway_markdown_report,
)

FORBIDDEN = (
    "Ready for Experimental Use",
    "Experimental Ready",
    "Potential bottleneck signal",
    "confirmed bottleneck",
    "Bottleneck identified",
    "bottleneck",
    "Predicted yield",
    "Predicted production",
    "Recommended optimization",
    "Automatically optimized pathway",
    "Yield will improve",
    "This is the bottleneck",
    "yield prediction",
    "production prediction",
    "automatic optimization",
    "optimized pathway",
    "ready for experiment",
    "Missing fields:",
    "Sequence present:",
    "Record count:",
    "{",
    "['",
)

REVIEW_NOTES_FORBIDDEN = (
    "Approved",
    "Ready",
    "Certified",
    "Validated",
    "Experimentally confirmed",
    "Lab-ready",
    "Release",
    "Pass/fail",
    "Sign-off complete",
)


def _project() -> dict:
    return {
        "id": 7,
        "name": "Naringenin Documentation Workspace",
        "target_product": "Naringenin",
        "host": "E. coli BL21(DE3)",
        "status": "draft",
        "description": "Local pathway documentation workspace.",
        "created_at": "2026-05-20 10:00",
        "updated_at": "2026-05-22 14:00",
    }


def _project_with_empty_review() -> dict:
    project = _project()
    project["documentation_review"] = {
        "review_items": {
            "pathway_description_reviewed": False,
            "gene_entries_reviewed": False,
            "linked_expression_designs_reviewed": False,
            "suggestions_reviewed": False,
            "test_records_reviewed": False,
            "markdown_documentation_report_reviewed": False,
            "unresolved_documentation_items_reviewed": False,
        },
        "reviewer_name_or_initials": "",
        "review_date": "",
        "review_notes": "",
        "follow_up_actions": "",
        "unresolved_items": "",
        "last_updated": "",
        "review_scope": "",
        "review_context": "",
    }
    return project


def _project_with_documentation_review() -> dict:
    project = _project_with_empty_review()
    project["documentation_review"] = {
        "review_items": {
            "pathway_description_reviewed": True,
            "gene_entries_reviewed": False,
            "linked_expression_designs_reviewed": True,
            "suggestions_reviewed": False,
            "test_records_reviewed": True,
            "markdown_documentation_report_reviewed": True,
            "unresolved_documentation_items_reviewed": False,
        },
        "reviewer_name_or_initials": "AB",
        "review_date": "2026-05-22",
        "review_notes": "Reviewed local documentation records and assumptions.",
        "follow_up_actions": "Clarify enzyme source notes.",
        "unresolved_items": "One source citation remains open.",
        "last_updated": "2026-05-22T10:30:00",
        "review_scope": "Local documentation review",
        "review_context": "Report integration test",
    }
    return project


def _steps(reaction_name: str = "Activation reaction") -> list[dict]:
    return [
        {
            "id": 10,
            "project_id": 7,
            "step_order": 1,
            "step_name": "Precursor activation",
            "reaction_name": reaction_name,
            "substrate": "Compound A",
            "product": "Compound B",
            "enzyme_name": "Enzyme A",
            "gene_name": "geneA",
            "gene_sequence": "ATGAAACCCGGGTAA",
            "organism_source": "Organism A",
            "notes": "Documented step note.",
        }
    ]


def _expression_links() -> list[dict]:
    return [
        {
            "id": 100,
            "project_id": 7,
            "step_id": 10,
            "design_id": 42,
            "design_name": "geneA expression design",
            "validation_summary_json": {
                "warnings": ["Recorded Wizard warning"],
                "primer_risk": "not recommended primer risk remains recorded",
            },
            "updated_at": "2026-05-22 13:00",
        }
    ]


def _test_records() -> list[dict]:
    return [
        {
            "id": 200,
            "project_id": 7,
            "step_id": 10,
            "sample_name": "Observation sample",
            "measured_product": "Naringenin",
            "titer": "120 mg/L user note",
            "yield_value": "0.18 g/g user note",
            "productivity": "4.2 mg/L/h user note",
            "intermediate_accumulation": "Qualitative user observation",
            "enzyme_activity": "Recorded user observation",
            "growth_status": "Normal user observation",
            "condition": "Shake flask note",
            "notes": "Observation only.",
        }
    ]


def _completeness(score: int = 75) -> dict:
    return {
        "score": score,
        "status": "In Progress",
        "missing_items": ["Step 1 has no linked expression design."],
        "step_summaries": [
            {
                "step_id": 10,
                "step_order": 1,
                "step_name": "Precursor activation",
                "score": score,
                "missing_items": ["Step 1 has no linked expression design."],
                "has_expression_design": False,
            }
        ],
    }


def _suggestions() -> list[dict]:
    return [
        {
            "signal_type": "missing_expression_design",
            "priority": "medium_review",
            "scope": "step-level",
            "related_step_id": 10,
            "message": "Review whether an expression design link should be documented for this step.",
            "evidence": {
                "step_id": 10,
                "step_name": "Precursor activation",
                "link_status": "missing",
                "sequence_doc_status": "missing",
                "test_record_status": "missing",
            },
            "suggested_next_check": "Review documentation completeness for the linked design field.",
            "boundary_note": "Documentation-only review signal. This does not certify experimental readiness.",
        }
    ]


def _report(**overrides) -> str:
    data = {
        "project": _project(),
        "steps": _steps(),
        "expression_links": _expression_links(),
        "test_records": _test_records(),
        "completeness_result": _completeness(),
        "suggestions": _suggestions(),
        "generated_at": datetime(2026, 5, 22, 14, 30, 0),
    }
    data.update(overrides)
    return generate_pathway_markdown_report(**data)


def _section(report: str, heading: str) -> str:
    start = report.index(heading)
    next_heading = report.find("\n\n## ", start + len(heading))
    if next_heading == -1:
        return report[start:]
    return report[start:next_heading]


def test_report_contains_required_sections():
    report = _report()

    required_sections = [
        "# Pathway Documentation Report",
        "Generated: 2026-05-22 14:30",
        "## Project Summary",
        "## Documentation-Only Boundary Statement",
        "## Pathway Steps",
        "## Linked Expression Wizard Design Summary",
        "## Test Records Summary",
        "## Completeness Summary",
        "## Suggestions / Review Signals Summary",
        "## Known Limitations",
    ]
    for section in required_sections:
        assert section in report


def test_report_uses_existing_recorded_data_only():
    report = _report()

    assert "Naringenin Documentation Workspace" in report
    assert "Compound A" in report
    assert "Compound B" in report
    assert "geneA expression design" in report
    assert "Observation sample" in report
    assert "120 mg/L user note" in report
    assert "Review whether an expression design link should be documented for this step." in report
    assert "Predicted" not in report
    assert "yield prediction" not in report.lower()
    assert "optimized pathway" not in report.lower()
    assert "ready for experiment" not in report.lower()


def test_report_handles_empty_sections_safely():
    report = _report(project={}, steps=[], expression_links=[], test_records=[], completeness_result={}, suggestions=[])

    assert "Untitled Pathway Project" in report
    assert "No pathway steps were provided." in report
    assert "No linked Expression Wizard designs were provided." in report
    assert "No Test Records were provided." in report
    assert "No step-level completeness summaries were provided." in report
    assert "No Suggestions / review signals were provided." in report


def test_empty_documentation_review_data_is_omitted_from_report():
    report_without_review_key = _report(project=_project())
    report_with_empty_review = _report(project=_project_with_empty_review())

    assert "## User-Authored Documentation Review Notes" not in report_without_review_key
    assert "## User-Authored Documentation Review Notes" not in report_with_empty_review
    assert REVIEW_NOTES_BOUNDARY_STATEMENT not in report_without_review_key
    assert REVIEW_NOTES_BOUNDARY_STATEMENT not in report_with_empty_review


def test_populated_documentation_review_data_is_included_in_report():
    report = _report(project=_project_with_documentation_review())

    assert "## User-Authored Documentation Review Notes" in report
    assert "### Review Metadata" in report
    assert "| Reviewer name or initials | AB |" in report
    assert "| Review date | 2026-05-22 |" in report
    assert "| Last updated | 2026-05-22T10:30:00 |" in report
    assert "### Review Notes" in report
    assert "Reviewed local documentation records and assumptions." in report
    assert "### Follow-Up Actions" in report
    assert "Clarify enzyme source notes." in report
    assert "### Unresolved Documentation Items" in report
    assert "One source citation remains open." in report


def test_review_notes_disclaimer_appears_exactly_when_section_is_rendered():
    populated_report = _report(project=_project_with_documentation_review())
    empty_report = _report(project=_project_with_empty_review())

    assert populated_report.count(REVIEW_NOTES_BOUNDARY_STATEMENT) == 1
    assert REVIEW_NOTES_BOUNDARY_STATEMENT not in empty_report


def test_review_notes_checklist_renders_documentation_state_only():
    report = _report(project=_project_with_documentation_review())
    section = report.split("## User-Authored Documentation Review Notes", 1)[1].split("## Known Limitations", 1)[0]

    assert "| Documentation item | User-marked state |" in section
    assert "| Pathway description reviewed for documentation completeness | Checked |" in section
    assert "| Gene entries reviewed for documentation completeness | Unchecked |" in section
    assert "| Linked Expression Wizard designs reviewed for documentation completeness | Checked |" in section
    assert "| Suggestions reviewed as documentation-only review signals | Unchecked |" in section
    assert "| Test Records reviewed | Checked |" in section
    assert "| Markdown Documentation Report reviewed | Checked |" in section
    assert "| Unresolved documentation items and follow-up actions reviewed | Unchecked |" in section
    assert "Pass" not in section
    assert "Fail" not in section


def test_forbidden_positive_authorization_wording_is_absent_from_review_notes_section():
    report = _report(project=_project_with_documentation_review())
    section = report.split("## User-Authored Documentation Review Notes", 1)[1].split("## Known Limitations", 1)[0]

    for phrase in REVIEW_NOTES_FORBIDDEN:
        assert phrase not in section
    for phrase in [
        "Potential bottleneck signal",
        "bottleneck",
        "yield prediction",
        "production prediction",
        "automatic optimization",
        "optimized pathway",
        "ready for experiment",
        "Missing fields:",
        "Sequence present:",
        "Record count:",
        "['",
    ]:
        assert phrase not in section


def test_existing_report_sections_remain_present_with_documentation_review_data():
    report = _report(project=_project_with_documentation_review())

    for section in [
        "# Pathway Documentation Report",
        "## Project Summary",
        "## Documentation-Only Boundary Statement",
        "## Pathway Steps",
        "## Linked Expression Wizard Design Summary",
        "## Test Records Summary",
        "## Completeness Summary",
        "## Suggestions / Review Signals Summary",
        "## User-Authored Documentation Review Notes",
        "## Known Limitations",
    ]:
        assert section in report


def test_markdown_table_values_are_escaped():
    project = _project()
    project["name"] = "Pipe | Project\nSecond Line"
    steps = _steps()
    steps[0]["notes"] = "Value | with pipe\nand newline"

    report = _report(project=project, steps=steps)

    assert "Pipe \\| Project<br>Second Line" in report
    assert "Value \\| with pipe<br>and newline" in report


def test_report_does_not_mutate_inputs():
    project = _project()
    steps = _steps()
    expression_links = _expression_links()
    test_records = _test_records()
    completeness = _completeness()
    suggestions = _suggestions()
    before = copy.deepcopy((project, steps, expression_links, test_records, completeness, suggestions))

    generate_pathway_markdown_report(
        project,
        steps,
        expression_links,
        test_records,
        completeness,
        suggestions,
        generated_at=datetime(2026, 5, 22, 14, 30, 0),
    )

    assert (project, steps, expression_links, test_records, completeness, suggestions) == before


def test_required_boundary_language_appears():
    report = _report()

    required = [
        "This report is documentation-only",
        "This is not an experimental conclusion or readiness assessment",
        "Completeness score means documentation coverage only",
        "Test Records are user-entered observations only",
        "Suggestions are rule-based transient review signals only",
        "Linked Expression Wizard designs are traceability links only",
        "Wizard validation, Step 6 export rules, and primer-risk semantics",
        "does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status",
        "does not include ML, Agent behavior, external database search, output estimation, production forecasting, or automated design-improvement guidance",
        "does not provide biological performance diagnosis",
    ]
    for text in required:
        assert text in report


def test_forbidden_wording_is_absent_from_generated_report_output():
    report = _report()

    lowered = report.lower()
    for phrase in FORBIDDEN:
        assert phrase.lower() not in lowered


def test_forbidden_wording_from_user_data_is_rewritten_or_redacted_from_report_output():
    project = _project()
    project["description"] = "Predicted yield and This is the bottleneck should not be exported."
    suggestions = _suggestions()
    suggestions[0]["message"] = "Potential bottleneck signal in user-entered fixture."
    suggestions[0]["boundary_note"] = "Please confirm a bottleneck if needed."

    report = _report(project=project, suggestions=suggestions)

    assert "[redacted unsafe wording]" in report
    assert "Documentation review prompt" in report
    assert "Missing recorded sequence" not in report
    assert "review the documentation gap" not in report
    assert "[redacted unsafe wording]" in report.lower()
    lowered = report.lower()
    for phrase in FORBIDDEN:
        assert phrase.lower() not in lowered


def test_completeness_score_is_displayed_from_passed_result_only():
    report = _report(completeness_result=_completeness(score=33), test_records=[])

    assert "| Score | 33% |" in report
    assert "Step 1 has no linked expression design." in report
    assert "| 1 | Precursor activation | 33 | No | 1 |" in report


def test_test_records_do_not_affect_completeness_semantics():
    completeness = _completeness(score=75)
    report_without_records = _report(completeness_result=completeness, test_records=[])
    report_with_records = _report(completeness_result=completeness, test_records=_test_records())

    assert "| Score | 75% |" in report_without_records
    assert "| Score | 75% |" in report_with_records
    assert "Test Records are user-entered observations only" in report_with_records
    assert "do not change completeness score semantics" in report_with_records


def test_suggestions_are_included_as_documentation_only_review_signals():
    report = _report()

    assert "missing_expression_design" in report
    assert "medium_review" in report
    assert "Suggestions are rule-based transient review signals only" in report
    assert "not predictions" in report
    assert "optimization instructions" in report
    assert "documentation gap" not in report
    assert "Sequence documentation is not recorded for this step." in report
    assert "No step-associated test record is recorded for this step." in report
    assert "Documentation-only review signal" in report
    assert "review the documentation gap" not in report


def test_linked_wizard_design_with_primer_risk_remains_non_certified():
    report = _report()

    assert "not recommended primer risk remains recorded" in report
    assert "Linked Expression Wizard designs are traceability links only" in report
    assert "Linked designs remain governed by Wizard validation, Step 6 export rules, and primer-risk semantics" in report
    assert "does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status" in report
    assert "pathway-level readiness" in report
    assert "certify experimental readiness" in report


def test_service_does_not_import_forbidden_dependencies_or_call_generators():
    import services.pathway_report_service as module

    source = inspect.getsource(module)
    forbidden_tokens = [
        "streamlit",
        "pathway_repository",
        "create_pathway",
        "update_pathway",
        "delete_pathway",
        "build_pathway_completeness",
        "analyze_pathway_bottlenecks",
        "sqlite3",
        "st.",
        "FPDF",
        "docx",
        "weasyprint",
        "pdfkit",
    ]
    for token in forbidden_tokens:
        assert token not in source


def test_review_notes_do_not_change_passed_completeness_or_suggestions_output():
    report = _report(project=_project_with_documentation_review(), completeness_result=_completeness(score=64))

    assert "| Score | 64% |" in report
    assert "Review whether an expression design link should be documented for this step." in report
    assert "missing_expression_design" in report
    assert "User-Authored Documentation Review Notes" in report


def test_report_service_signature_keeps_generation_input_only():
    signature = inspect.signature(generate_pathway_markdown_report)

    assert list(signature.parameters) == [
        "project",
        "steps",
        "expression_links",
        "test_records",
        "completeness_result",
        "suggestions",
        "generated_at",
        "config",
    ]


def test_config_none_matches_default_config_output():
    assert _report(config=None) == _report(config=PathwayReportConfig())


def test_default_config_preserves_current_report_sections():
    report = _report(config=PathwayReportConfig())

    for section in [
        "## Project Summary",
        "## Pathway Steps",
        "## Linked Expression Wizard Design Summary",
        "## Test Records Summary",
        "## Completeness Summary",
        "## Suggestions / Review Signals Summary",
        "## Known Limitations",
    ]:
        assert section in report
    assert OPTIONAL_SECTION_OMISSION_NOTICE not in report
    assert "ATGAAACCCGGGTAA" not in report
    assert "Recorded (15 nt)" in report


def test_each_optional_section_can_be_disabled_independently():
    cases = [
        (PathwayReportConfig(include_project_metadata=False), "## Project Summary"),
        (PathwayReportConfig(include_pathway_steps=False), "## Pathway Steps"),
        (PathwayReportConfig(include_linked_designs=False), "## Linked Expression Wizard Design Summary"),
        (PathwayReportConfig(include_test_records=False), "## Test Records Summary"),
        (PathwayReportConfig(include_suggestions=False), "## Suggestions / Review Signals Summary"),
        (PathwayReportConfig(include_review_notes=False), "## User-Authored Documentation Review Notes"),
    ]

    for config, omitted_heading in cases:
        report = _report(project=_project_with_documentation_review(), config=config)
        assert omitted_heading not in report
        assert OPTIONAL_SECTION_OMISSION_NOTICE in report
        assert "## Documentation-Only Boundary Statement" in report
        assert "## Known Limitations" in report
        assert "## Completeness Summary" in report


def test_mandatory_safety_language_remains_when_all_optional_sections_disabled():
    config = PathwayReportConfig(
        include_project_metadata=False,
        include_pathway_steps=False,
        include_linked_designs=False,
        include_test_records=False,
        include_suggestions=False,
        include_review_notes=False,
    )
    report = _report(project=_project_with_documentation_review(), config=config)

    assert "## Project Summary" not in report
    assert "## Pathway Steps" not in report
    assert "## Linked Expression Wizard Design Summary" not in report
    assert "## Test Records Summary" not in report
    assert "## Suggestions / Review Signals Summary" not in report
    assert "## User-Authored Documentation Review Notes" not in report
    for required in [
        "This report is documentation-only",
        "does not certify experimental readiness",
        "Completeness score means documentation coverage only",
        "does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status",
        "does not include ML, Agent behavior, external database search, output estimation, production forecasting, or automated design-improvement guidance",
        "## Completeness Summary",
        "## Known Limitations",
        OPTIONAL_SECTION_OMISSION_NOTICE,
    ]:
        assert required in report


def test_omission_notice_appears_when_any_optional_section_is_disabled():
    report = _report(config=PathwayReportConfig(include_suggestions=False))

    assert OPTIONAL_SECTION_OMISSION_NOTICE in report


def test_omission_notice_does_not_appear_with_default_sections():
    assert OPTIONAL_SECTION_OMISSION_NOTICE not in _report()
    assert OPTIONAL_SECTION_OMISSION_NOTICE not in _report(config=PathwayReportConfig())


def test_full_gene_sequences_are_absent_by_default():
    report = _report()

    assert "ATGAAACCCGGGTAA" not in report
    assert "Recorded (15 nt)" in report
    assert "Full gene sequence text was user-selected" not in report


def test_full_gene_sequences_appear_only_when_enabled():
    disabled_report = _report(config=PathwayReportConfig(include_full_gene_sequences=False))
    enabled_report = _report(config=PathwayReportConfig(include_full_gene_sequences=True))

    assert "ATGAAACCCGGGTAA" not in disabled_report
    assert "Recorded (15 nt)" in disabled_report
    assert "ATGAAACCCGGGTAA" in enabled_report
    assert "Recorded (15 nt)" not in _section(enabled_report, "## Pathway Steps")
    assert "Full gene sequence text was user-selected for this Markdown report" in enabled_report


def test_enabling_full_gene_sequences_does_not_remove_mandatory_safety_language():
    report = _report(config=PathwayReportConfig(include_full_gene_sequences=True))

    for required in [
        "This report is documentation-only",
        "does not certify experimental readiness",
        "does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status",
        "## Known Limitations",
    ]:
        assert required in report


def test_disabling_suggestions_omits_only_suggestions_and_does_not_mutate_input():
    suggestions = _suggestions()
    before = copy.deepcopy(suggestions)
    report = _report(suggestions=suggestions, config=PathwayReportConfig(include_suggestions=False))

    assert "## Suggestions / Review Signals Summary" not in report
    assert "Review whether an expression design link should be documented for this step." not in report
    assert "## Test Records Summary" in report
    assert "## Completeness Summary" in report
    assert suggestions == before


def test_disabling_test_records_omits_only_records_and_preserves_completeness_output():
    report = _report(config=PathwayReportConfig(include_test_records=False), completeness_result=_completeness(score=81))

    assert "## Test Records Summary" not in report
    assert "Observation sample" not in report
    assert "## Completeness Summary" in report
    assert "| Score | 81% |" in report
    assert "## Suggestions / Review Signals Summary" in report


def test_disabling_review_notes_omits_only_review_notes_and_does_not_mutate_project_review():
    project = _project_with_documentation_review()
    before = copy.deepcopy(project["documentation_review"])
    report = _report(project=project, config=PathwayReportConfig(include_review_notes=False))

    assert "## User-Authored Documentation Review Notes" not in report
    assert "Reviewed local documentation records and assumptions." not in report
    assert "## Suggestions / Review Signals Summary" in report
    assert project["documentation_review"] == before


def test_disabling_linked_designs_keeps_report_level_safety_language():
    report = _report(config=PathwayReportConfig(include_linked_designs=False))

    assert "## Linked Expression Wizard Design Summary" not in report
    assert "not recommended primer risk remains recorded" not in report
    assert "Wizard validation, Step 6 export rules, and primer-risk semantics" in report
    assert "does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status" in report
    assert "does not certify experimental readiness" in report


def test_disabling_pathway_steps_does_not_change_completeness_section_output():
    default_report = _report(completeness_result=_completeness(score=59))
    configured_report = _report(
        completeness_result=_completeness(score=59),
        config=PathwayReportConfig(include_pathway_steps=False),
    )

    assert "## Pathway Steps" not in configured_report
    assert _section(default_report, "## Completeness Summary") == _section(configured_report, "## Completeness Summary")


def test_disabling_project_metadata_does_not_introduce_identity_or_audit_language():
    report = _report(config=PathwayReportConfig(include_project_metadata=False))

    assert "## Project Summary" not in report
    forbidden = ["Report ID", "Audit", "Electronic Signature", "Signature", "Report History", "Saved Configuration"]
    for phrase in forbidden:
        assert phrase not in report


def test_no_new_export_persistence_or_saved_config_language_is_introduced():
    report = _report(config=PathwayReportConfig(include_project_metadata=False, include_suggestions=False))
    source = inspect.getsource(__import__("services.pathway_report_service", fromlist=["dummy"]))

    forbidden = [
        "PDF export",
        "DOCX export",
        "HTML export",
        "report persistence",
        "config persistence",
        "saved report configuration",
        "report history",
        "approval workflow",
        "electronic signature",
    ]
    combined = f"{report}\n{source}"
    for phrase in forbidden:
        assert phrase.lower() not in combined.lower()


def test_no_positive_approval_readiness_certification_prediction_or_optimization_claims_are_introduced():
    report = _report(config=PathwayReportConfig(include_full_gene_sequences=True))

    forbidden_positive_claims = [
        "approved for experimental use",
        "certifies experimental readiness",
        "certified ready",
        "validated for experimental use",
        "predicts improved yield",
        "optimization recommendation",
        "this report confirms bottlenecks",
    ]
    for phrase in forbidden_positive_claims:
        assert phrase not in report.lower()


def test_generated_timestamp_uses_compact_display_and_can_be_omitted():
    report_with_timestamp = _report(generated_at=datetime(2026, 5, 22, 14, 30, 0))
    report_without_timestamp = _report(generated_at=None)

    assert "Generated: 2026-05-22 14:30" in report_with_timestamp
    assert "Generated: Not provided" not in report_with_timestamp
    assert "Generated:" not in report_without_timestamp


def test_reaction_column_prefers_reaction_name_and_derives_from_substrate_product_when_missing():
    report_with_reaction = _report()
    derived_report = _report(steps=_steps(reaction_name=""))

    assert "| 1 | Precursor activation | Activation reaction | Compound A | Compound B |" in report_with_reaction
    assert "| 1 | Precursor activation | Compound A → Compound B | Compound A | Compound B |" in derived_report
    assert "Not recorded" not in derived_report.split("## Pathway Steps", 1)[1]


def test_suggestion_evidence_is_rendered_as_human_readable_text():
    report = _report()
    suggestion_section = _section(report, "## Suggestions / Review Signals Summary")

    assert "No linked Expression Wizard design is recorded for this step." in suggestion_section
    assert "Sequence documentation is not recorded for this step." in suggestion_section
    assert "No step-associated test record is recorded for this step." in suggestion_section
    assert "{'step_id'" not in suggestion_section
    assert "Missing fields:" not in suggestion_section
    assert "Sequence present:" not in suggestion_section
    assert "Record count:" not in suggestion_section


def test_report_avoids_duplicate_test_record_rows_when_identical_entries_are_present():
    duplicate = _test_records()[0]
    variant = copy.deepcopy(duplicate)
    variant["sample_name"] = " observation   sample "
    variant["measured_product"] = "Naringenin!"
    variant["condition"] = "Shake flask note."
    variant["notes"] = "Observation only"
    report = _report(test_records=[duplicate, copy.deepcopy(duplicate), variant])
    section = _section(report, "## Test Records Summary")

    assert section.count("Observation sample") == 1
    assert section.count("| Step 1: Precursor activation | Observation sample |") == 1
