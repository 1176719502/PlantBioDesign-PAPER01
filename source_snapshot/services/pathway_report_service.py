from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import re

from services.report_identity_presenter import (
    build_report_identity_block,
    build_report_visual_narrative,
    format_report_identity_markdown,
    format_report_visual_narrative_markdown,
)
from services.pathway_completeness_service import (
    build_dbt_step_evidence_matrix_rows,
    build_pathway_review_signals,
    summarize_review_signals,
)

FORBIDDEN_REPORT_PHRASES = (
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
    "automatic optimization",
)

DOCUMENTATION_ONLY_REPLACEMENTS = (
    ("Potential bottleneck signal", "Documentation review prompt"),
    ("confirmed bottleneck", "Missing recorded sequence"),
    ("bottleneck", "documentation gap"),
    ("Bottleneck", "Documentation gap"),
    ("yield prediction", "Missing documentation link"),
    ("Yield prediction", "Missing documentation link"),
    ("optimized pathway", "Documentation gap"),
    ("Optimized pathway", "Documentation gap"),
    ("ready for experiment", "documentation review prompt"),
    ("Ready for experiment", "documentation review prompt"),
    ("confirm a bottleneck", "review the documentation gap"),
)

REDACTION_TEXT = "[redacted unsafe wording]"


@dataclass(frozen=True)
class PathwayReportConfig:
    include_project_metadata: bool = True
    include_pathway_steps: bool = True
    include_linked_designs: bool = True
    include_test_records: bool = True
    include_suggestions: bool = True
    include_review_notes: bool = True
    include_full_gene_sequences: bool = False

    def has_omitted_optional_sections(self) -> bool:
        return not all(
            (
                self.include_project_metadata,
                self.include_pathway_steps,
                self.include_linked_designs,
                self.include_test_records,
                self.include_suggestions,
                self.include_review_notes,
            )
        )


OPTIONAL_SECTION_OMISSION_NOTICE = (
    "Some optional documentation sections were omitted by user selection for this Markdown report. Omission does not "
    "change project data, validation status, completeness scoring, primer-risk status, or experimental readiness."
)


FULL_SEQUENCE_BOUNDARY_STATEMENT = (
    "Full gene sequence text was user-selected for this Markdown report. Sequence text is recorded documentation only; "
    "this report does not perform sequence analysis, validation, optimization, prediction, or experimental readiness "
    "certification."
)


TABLE_EMPTY_VALUE = "Not recorded"


BOUNDARY_STATEMENT = (
    "This report is documentation-only. This is not an experimental conclusion or readiness assessment. Completeness "
    "score means documentation coverage only. Test Records are user-entered observations only. Suggestions are "
    "rule-based transient review signals only. Documentation-only review signal. Linked Expression Wizard designs are "
    "traceability links only. Linked designs remain governed by Wizard validation, Step 6 export rules, and primer-risk "
    "semantics. The report does not reinterpret Wizard validation, Step 6 export recommendation, or primer-risk status. "
    "The report does not include ML, Agent behavior, external database search, output estimation, production forecasting, "
    "or automated design-improvement guidance. The report does not certify experimental readiness. The report does not "
    "predict yield. The report does not optimize pathways. The report does not introduce pathway-level readiness claims."
)


REVIEW_NOTES_BOUNDARY_STATEMENT = (
    "This section contains user-authored documentation review notes only. Checklist completion does not certify "
    "experimental readiness and does not override Wizard validation, primer-risk status, Step 6 export "
    "recommendations, completeness score, Suggestions, or downstream handoff boundaries."
)


BOUNDARY_STATEMENT_BULLETS = [
    "- This report is documentation-only.",
    "- This report does not certify experimental readiness.",
    "- This report does not predict yield.",
    "- This report does not optimize pathways.",
    "- This report does not replace expert review.",
    "- This report does not introduce pathway-level readiness claims.",
]


DOCUMENTATION_REVIEW_CHECKLIST_LABELS = {
    "pathway_description_reviewed": "Pathway description reviewed for documentation completeness",
    "gene_entries_reviewed": "Gene entries reviewed for documentation completeness",
    "linked_expression_designs_reviewed": "Linked Expression Wizard designs reviewed for documentation completeness",
    "suggestions_reviewed": "Suggestions reviewed as documentation-only review signals",
    "test_records_reviewed": "Test Records reviewed",
    "markdown_documentation_report_reviewed": "Markdown Documentation Report reviewed",
    "unresolved_documentation_items_reviewed": "Unresolved documentation items and follow-up actions reviewed",
}


KNOWN_LIMITATIONS = (
    "- This report is generated on demand from data passed into the report service.\n"
    "- This report is not saved to the database by this service.\n"
    "- This report does not include ML, Agent behavior, external database search, output estimation, or automated "
    "design-improvement guidance.\n"
    "- This report does not certify experimental readiness.\n"
    "- This report does not provide biological performance diagnosis.\n"
    "- This report does not reinterpret linked Wizard validation, Step 6 export rules, Step 6 export recommendation, "
    "or primer-risk semantics.\n"
    "- This report does not introduce pathway-level readiness claims."
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _format_generated_at(generated_at: Any) -> str:
    if isinstance(generated_at, datetime):
        return generated_at.strftime("%Y-%m-%d %H:%M")
    if isinstance(generated_at, date):
        return datetime.combine(generated_at, datetime.min.time()).strftime("%Y-%m-%d %H:%M")
    return ""


def _safe_text(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, (dict, list, tuple, set)):
        text = str(value)
    else:
        text = str(value)
    for phrase, replacement in DOCUMENTATION_ONLY_REPLACEMENTS:
        text = text.replace(phrase, replacement)
    for phrase in FORBIDDEN_REPORT_PHRASES:
        text = text.replace(phrase, REDACTION_TEXT)
    return text.strip()


def _safe_inline(value: Any, empty: str = TABLE_EMPTY_VALUE) -> str:
    text = _safe_text(value)
    if not text:
        return empty
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _sequence_presence_and_length(sequence: Any) -> str:
    text = _safe_text(sequence).replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    if not text:
        return "Not recorded"
    return f"Recorded ({len(text)} nt)"


def _table(headers: list[str], rows: list[list[Any]], empty_message: str) -> str:
    if not rows:
        return empty_message
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_safe_inline(value) for value in row) + " |")
    return "\n".join(lines)


def _step_label(step_id: Any, steps_by_id: dict[int, dict[str, Any]]) -> str:
    try:
        resolved_step_id = int(step_id)
    except (TypeError, ValueError):
        return "Project-level"
    step = steps_by_id.get(resolved_step_id)
    if not step:
        return f"Step {resolved_step_id}"
    order = step.get("step_order") or resolved_step_id
    name = step.get("step_name") or step.get("reaction_name") or step.get("product") or f"Step {order}"
    return f"Step {order}: {name}"


def _build_project_summary(project: dict[str, Any]) -> str:
    rows = [
        ["Project ID", project.get("id")],
        ["Project Name", project.get("name")],
        ["Target Product", project.get("target_product")],
        ["Host / Chassis", project.get("host")],
        ["Status", project.get("status")],
        ["Description", project.get("description")],
        ["Created", project.get("created_at")],
        ["Updated", project.get("updated_at")],
    ]
    return _table(["Field", "Value"], rows, "No project metadata was provided.")


def _derive_reaction_label(step: dict[str, Any]) -> str:
    reaction_name = _safe_text(step.get("reaction_name"))
    if reaction_name:
        return reaction_name
    substrate = _safe_text(step.get("substrate"))
    product = _safe_text(step.get("product"))
    if substrate and product:
        return f"{substrate} → {product}"
    return TABLE_EMPTY_VALUE


def _build_steps_table(steps: list[dict[str, Any]], include_full_gene_sequences: bool = False) -> str:
    sequence_value = _safe_text if include_full_gene_sequences else _sequence_presence_and_length
    rows = [
        [
            step.get("step_order"),
            step.get("step_name") or f"Step {step.get('step_order') or step.get('id') or ''}".strip(),
            _derive_reaction_label(step),
            step.get("substrate"),
            step.get("product"),
            step.get("enzyme_name"),
            step.get("gene_name"),
            sequence_value(step.get("gene_sequence")),
            step.get("organism_source"),
            step.get("notes"),
        ]
        for step in steps
    ]
    return _table(
        ["Order", "Step", "Reaction", "Substrate", "Product", "Enzyme", "Gene", "Sequence", "Source", "Notes"],
        rows,
        "No pathway steps were provided.",
    )


def _summarize_validation_summary(value: Any) -> str:
    summary = _as_mapping(value)
    if not summary:
        return TABLE_EMPTY_VALUE
    parts: list[str] = []
    warnings = summary.get("warnings")
    if isinstance(warnings, list) and warnings:
        parts.append(f"Warnings recorded: {len(warnings)}")
    primer_risk = _safe_text(summary.get("primer_risk"))
    if primer_risk:
        parts.append(f"Primer risk: {primer_risk}")
    return "; ".join(parts) if parts else TABLE_EMPTY_VALUE


def _build_expression_links_table(expression_links: list[dict[str, Any]], steps_by_id: dict[int, dict[str, Any]]) -> str:
    rows = [
        [
            _step_label(link.get("step_id"), steps_by_id),
            link.get("design_id") or link.get("id"),
            link.get("design_name") or link.get("name"),
            _summarize_validation_summary(link.get("validation_summary_json") or link.get("validation_summary")),
            link.get("primer_risk") or _as_mapping(link.get("validation_summary_json")).get("primer_risk"),
            link.get("updated_at") or link.get("created_at"),
        ]
        for link in expression_links
    ]
    return _table(
        ["Step", "Design ID", "Design Name", "Recorded Validation Summary", "Recorded Primer Risk", "Updated"],
        rows,
        "No linked Expression Wizard designs were provided.",
    )


def _build_linked_design_summary(expression_links: list[dict[str, Any]], steps_by_id: dict[int, dict[str, Any]]) -> str:
    if not expression_links:
        return "No linked Expression Wizard designs were provided."

    sections = ["### Linked Design Summary"]
    for link in expression_links:
        sections.append(
            "\n".join(
                [
                    f"- Step: {_step_label(link.get('step_id'), steps_by_id)}",
                    f"  - Design ID: {link.get('design_id') or link.get('id')}",
                    f"  - Design Name: {link.get('design_name') or link.get('name') or TABLE_EMPTY_VALUE}",
                    f"  - Recorded Validation Summary: {_summarize_validation_summary(link.get('validation_summary_json') or link.get('validation_summary'))}",
                    f"  - Recorded Primer Risk: {link.get('primer_risk') or _as_mapping(link.get('validation_summary_json')).get('primer_risk') or TABLE_EMPTY_VALUE}",
                ]
            )
        )
    return "\n\n".join(sections)


def _normalized_report_key(value: Any) -> str:
    text = _safe_text(value).lower().strip()
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_test_records_table(test_records: list[dict[str, Any]], steps_by_id: dict[int, dict[str, Any]]) -> str:
    rows = []
    seen_rows: set[tuple[str, ...]] = set()
    for record in test_records:
        row = [
            _step_label(record.get("step_id"), steps_by_id),
            record.get("sample_name"),
            record.get("measured_product"),
            record.get("titer"),
            record.get("yield_value") or record.get("yield"),
            record.get("productivity"),
            record.get("intermediate_accumulation"),
            record.get("enzyme_activity"),
            record.get("growth_status"),
            record.get("condition"),
            record.get("notes"),
        ]
        dedupe_key = tuple(_normalized_report_key(value) for value in row)
        if dedupe_key in seen_rows:
            continue
        seen_rows.add(dedupe_key)
        rows.append(row)
    return _table(
        [
            "Scope",
            "Sample",
            "Measured Product",
            "Titer Observation",
            "Yield Observation",
            "Productivity Observation",
            "Intermediate Accumulation",
            "Enzyme Activity",
            "Growth Status",
            "Condition",
            "Notes",
        ],
        rows,
        "No Test Records were provided.",
    )


def _build_completeness_summary(completeness_result: dict[str, Any]) -> str:
    missing_items = completeness_result.get("missing_items")
    if isinstance(missing_items, list):
        missing_text = "; ".join(_safe_text(item) for item in missing_items) or "None recorded"
    else:
        missing_text = missing_items

    summary = _table(
        ["Field", "Value"],
        [
            ["Score", f"{completeness_result.get('score', TABLE_EMPTY_VALUE)}%" if completeness_result.get("score") is not None else TABLE_EMPTY_VALUE],
            ["Status", completeness_result.get("status")],
            ["Missing Items", missing_text],
        ],
        "No completeness summary was provided.",
    )

    step_summaries = _as_records(completeness_result.get("step_summaries"))
    step_rows = [
        [
            item.get("step_order"),
            item.get("step_name"),
            item.get("score"),
            "Yes" if item.get("has_expression_design") else "No",
            len(item.get("missing_items") or []),
        ]
        for item in step_summaries
    ]
    step_table = _table(
        ["Order", "Step", "Score", "Expression Design Linked", "Missing Count"],
        step_rows,
        "No step-level completeness summaries were provided.",
    )
    return f"{summary}\n\n### Step Completeness\n\n{step_table}"


def _format_evidence(evidence: Any, steps_by_id: dict[int, dict[str, Any]]) -> str:
    if isinstance(evidence, str):
        text = evidence.strip()
        return text or TABLE_EMPTY_VALUE
    if not isinstance(evidence, dict):
        return TABLE_EMPTY_VALUE

    step_id = evidence.get("step_id")
    step_label = _step_label(step_id, steps_by_id)
    step_label_lower = step_label.lower()
    parts: list[str] = []

    if evidence.get("sequence_present") is False or evidence.get("sequence_doc_status") in {"missing", "not recorded", "absent"}:
        parts.append("Sequence documentation is not recorded for this step.")
    if evidence.get("linked_design_present") is False or evidence.get("link_status") in {"missing", "not linked", "unlinked"}:
        parts.append("No linked Expression Wizard design is recorded for this step.")
    if evidence.get("test_record_count") == 0 or evidence.get("test_record_status") in {"missing", "not recorded", "absent"}:
        parts.append("No step-associated test record is recorded for this step.")

    if not parts:
        return "No missing documentation recorded."

    return " ".join(parts)


def _build_suggestions_table(suggestions: list[dict[str, Any]], steps_by_id: dict[int, dict[str, Any]]) -> str:
    rows = [
        [
            signal.get("signal_type"),
            signal.get("priority"),
            signal.get("scope"),
            _step_label(signal.get("related_step_id"), steps_by_id),
            signal.get("message"),
            _format_evidence(signal.get("evidence"), steps_by_id),
            signal.get("suggested_next_check"),
            signal.get("boundary_note"),
        ]
        for signal in suggestions
    ]
    return _table(
        ["Signal Type", "Priority", "Scope", "Related Step", "Message", "Evidence", "Suggested Next Check", "Boundary Note"],
        rows,
        "No Suggestions / review signals were provided.",
    )


def _build_review_signals_section(review_signals: list[dict[str, Any]], steps_by_id: dict[int, dict[str, Any]]) -> str:
    rows = [
        [
            signal.get("signal_type"),
            signal.get("priority"),
            signal.get("scope"),
            _step_label(signal.get("related_step_id"), steps_by_id),
            signal.get("message"),
            _format_evidence(signal.get("evidence"), steps_by_id),
        ]
        for signal in review_signals
    ]
    return _table(
        ["Signal Type", "Priority", "Scope", "Related Step", "Message", "Evidence"],
        rows,
        "No Suggestions / review signals were provided.",
    )


def _is_checked(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else str(value or "").strip().lower() == "true"


def _review_text_field(review: dict[str, Any], field: str) -> str:
    return _safe_text(review.get(field))


def _has_documentation_review_data(review: dict[str, Any]) -> bool:
    review_items = _as_mapping(review.get("review_items"))
    text_fields = (
        "reviewer_name_or_initials",
        "review_date",
        "last_updated",
        "review_notes",
        "follow_up_actions",
        "unresolved_items",
    )
    return any(_is_checked(review_items.get(key)) for key in DOCUMENTATION_REVIEW_CHECKLIST_LABELS) or any(
        _review_text_field(review, field) for field in text_fields
    )


def _build_documentation_review_section(project: dict[str, Any]) -> str:
    review = _as_mapping(project.get("documentation_review"))
    if not _has_documentation_review_data(review):
        return ""

    review_items = _as_mapping(review.get("review_items"))
    sections = [
        "## User-Authored Documentation Review Notes",
        REVIEW_NOTES_BOUNDARY_STATEMENT,
    ]

    metadata_rows = [
        ["Reviewer name or initials", review.get("reviewer_name_or_initials")],
        ["Review date", review.get("review_date")],
        ["Last updated", review.get("last_updated")],
    ]
    populated_metadata_rows = [row for row in metadata_rows if _safe_text(row[1])]
    if populated_metadata_rows:
        sections.extend(
            [
                "### Review Metadata",
                _table(["Field", "Value"], populated_metadata_rows, ""),
            ]
        )

    checklist_rows = [
        [label, "Checked" if _is_checked(review_items.get(key)) else "Unchecked"]
        for key, label in DOCUMENTATION_REVIEW_CHECKLIST_LABELS.items()
    ]
    sections.extend(
        [
            "### Manual Documentation Checklist",
            _table(["Documentation item", "User-marked state"], checklist_rows, ""),
        ]
    )

    text_sections = [
        ("### Review Notes", review.get("review_notes")),
        ("### Follow-Up Actions", review.get("follow_up_actions")),
        ("### Unresolved Documentation Items", review.get("unresolved_items")),
    ]
    for heading, value in text_sections:
        if _safe_text(value):
            sections.extend([heading, _safe_text(value)])

    return "\n\n".join(sections)


def generate_pathway_markdown_report(
    project: Any,
    steps: Any,
    expression_links: Any,
    test_records: Any,
    completeness_result: Any,
    suggestions: Any,
    generated_at: Any = None,
    config: PathwayReportConfig | None = None,
) -> str:
    report_config = config or PathwayReportConfig()
    safe_project = _as_mapping(project)
    safe_steps = _as_records(steps)
    safe_expression_links = _as_records(expression_links)
    safe_test_records = _as_records(test_records)
    safe_completeness = _as_mapping(completeness_result)
    explicit_suggestions_supplied = suggestions is not None
    safe_suggestions = _as_records(suggestions)
    if explicit_suggestions_supplied:
        review_signals = safe_suggestions if report_config.include_suggestions else []
    else:
        review_signals = build_pathway_review_signals(safe_project, safe_steps, safe_expression_links, safe_test_records) if report_config.include_suggestions else []
    steps_by_id = {
        int(step["id"]): step
        for step in safe_steps
        if str(step.get("id") or "").strip().isdigit()
    }
    review_signal_summary = summarize_review_signals(review_signals)
    evidence_matrix_rows = build_dbt_step_evidence_matrix_rows(safe_project, safe_steps, safe_expression_links, safe_test_records, review_signals)

    project_name = _safe_inline(safe_project.get("name"), "Untitled Pathway Project")
    generated_text = _format_generated_at(generated_at)
    report_identity = build_report_identity_block(
        report_title="Pathway Documentation Report",
        project_or_case_name=project_name,
        generated_at=generated_text or "Not recorded",
        report_version="Pathway Markdown Report",
        software_version="BioDesign Studio",
        report_or_package_id=f"pathway-report:{_safe_inline(safe_project.get('id'), 'local')}",
        purpose="Pathway documentation review, provenance review, and handoff communication.",
        review_stage=_safe_inline(safe_project.get("status"), "Documentation review stage not recorded"),
        recorded_context=(
            f"{len(safe_steps)} pathway step record(s), {len(safe_expression_links)} linked Expression Wizard design(s), "
            f"{len(safe_test_records)} user-entered observation record(s), {review_signal_summary['total_review_signals']} review signal(s)."
        ),
        manual_follow_up="Human/company review should resolve missing documentation fields, source/provenance notes, and handoff questions.",
    )
    visual_narrative = build_report_visual_narrative(
        stage=_safe_inline(safe_project.get("status"), "Documentation review stage not recorded"),
        recorded_context=(
            f"Pathway steps {len(safe_steps)}; linked designs {len(safe_expression_links)}; "
            f"review signals {review_signal_summary['total_review_signals']}."
        ),
        manual_follow_up="Manual/company follow-up remains responsible for source checks, unresolved documentation review items, and report interpretation.",
    )

    sections = [
        "# Pathway Documentation Report",
    ]
    if generated_text:
        sections.append(f"Generated: {generated_text}")
    sections.append(f"Project: {project_name}")
    sections.extend(
        [
            format_report_identity_markdown(report_identity),
            format_report_visual_narrative_markdown(visual_narrative),
        ]
    )

    if report_config.include_project_metadata:
        sections.extend([
            "## Project Summary",
            _build_project_summary(safe_project),
        ])

    sections.extend([
        "## Documentation-Only Boundary Statement",
        BOUNDARY_STATEMENT,
        "",
        "### Boundary Statement",
        "",
        *BOUNDARY_STATEMENT_BULLETS,
    ])

    if report_config.has_omitted_optional_sections():
        sections.extend([
            "## Optional Section Omission Notice",
            OPTIONAL_SECTION_OMISSION_NOTICE,
        ])

    if report_config.include_pathway_steps:
        sections.extend([
            "## Pathway Steps",
            *(
                [FULL_SEQUENCE_BOUNDARY_STATEMENT]
                if report_config.include_full_gene_sequences
                else []
            ),
            _build_steps_table(safe_steps, report_config.include_full_gene_sequences),
        ])

    if report_config.include_linked_designs:
        linked_design_summary = _build_linked_design_summary(safe_expression_links, steps_by_id)
        sections.extend([
            "## Linked Expression Wizard Design Summary",
            (
                "Linked Expression Wizard designs are traceability links only. Linked designs remain governed by Wizard "
                "validation, Step 6 export rules, and primer-risk semantics. This report does not reinterpret Wizard "
                "validation, Step 6 export recommendation, or primer-risk status."
            ),
            _build_expression_links_table(safe_expression_links, steps_by_id),
        ])
        if linked_design_summary != "No linked Expression Wizard designs were provided.":
            sections.append(linked_design_summary)

    if report_config.include_test_records:
        sections.extend([
            "## Test Records Summary",
            (
                "Test Records are user-entered observations only. They are not experimental validation, automated analysis, "
                "predictive results, or readiness certification, and they do not change completeness score semantics."
            ),
            _build_test_records_table(safe_test_records, steps_by_id),
        ])

    sections.extend([
        "## Completeness Summary",
        (
            "Completeness score means documentation coverage only. It is not biological performance, optimization quality, or readiness certification."
        ),
        _build_completeness_summary(safe_completeness),
    ])

    if report_config.include_suggestions:
        sections.extend([
            "## Suggestions / Review Signals Summary",
            (
                "Suggestions are rule-based review signals only. They are not predictions, experimental validation, optimization instructions, or experimental readiness certification. Documentation-only review signal. Suggestions are rule-based transient review signals only..."
            ),
            _build_review_signals_section(review_signals, steps_by_id),
        ])

    sections.extend([
        "## Review Signals Summary",
        _table(
            ["Metric", "Value"],
            [
                ["Total review signals", review_signal_summary["total_review_signals"]],
                ["High review", review_signal_summary["high_review_count"]],
                ["Medium review", review_signal_summary["medium_review_count"]],
                ["Info", review_signal_summary["info_count"]],
                ["Documentation gaps", review_signal_summary["documentation_gap_count"]],
                ["Missing test record prompts", review_signal_summary["missing_test_record_prompt_count"]],
            ],
            "No review signal summary was provided.",
        ),
        "## Evidence Matrix",
        _table(
            ["Step", "Sequence recorded?", "Expression design linked?", "Test record exists?", "Review signals", "Missing documentation summary"],
            [
                [
                    row.get("step_order"),
                    "Yes" if row.get("sequence_recorded") else "No",
                    "Yes" if row.get("expression_design_linked") else "No",
                    "Yes" if row.get("test_record_exists") else "No",
                    row.get("review_signal_count"),
                    row.get("missing_documentation_summary"),
                ]
                for row in evidence_matrix_rows
            ],
            "No evidence matrix rows were provided.",
        ),
    ])

    if report_config.include_review_notes:
        review_section = _build_documentation_review_section(safe_project)
        if review_section:
            sections.append(review_section)

    sections.extend([
        "## Known Limitations",
        KNOWN_LIMITATIONS,
    ])
    return "\n\n".join(_safe_text(section) for section in sections) + "\n"
