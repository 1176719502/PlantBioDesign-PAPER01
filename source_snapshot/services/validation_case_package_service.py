from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
    normalize_generated_output_text,
)
from services.placeholder_review_value import clean_review_value, is_placeholder_review_value


PACKAGE_TITLE = "Validation Case Package"
PACKAGE_SUBTITLE = (
    "Documentation-only pre-experiment package for teacher/company feasibility review."
)
CHECKSUM_ALGORITHM = "MD5"
QR_PAYLOAD_HEADER = "BioDesign Studio validation case package identity payload"
DEFAULT_EXPERIMENT_STATUS_PLACEHOLDER = (
    "Not started in BioDesign Studio; record external status after expert/company review."
)
DEFAULT_RESULT_SUMMARY_PLACEHOLDER = (
    "No experimental result summary recorded in BioDesign Studio."
)
DEFAULT_COMPANY_FEEDBACK_PLACEHOLDER = (
    "Company feasibility feedback placeholder: record external feasibility notes, requested clarifications, "
    "or constraints after human review."
)
BOUNDARY_NOTES = [
    "This package supports pre-experiment documentation and feasibility review.",
    "It is not a wet-lab protocol.",
    "It does not guarantee expression.",
    "It does not forecast yield or experimental success.",
    "It does not select a preferred expression system.",
    "It does not replace expert/company review.",
    "It does not perform codon rewriting or automatic conservation classification.",
]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    clean = normalize_generated_output_text(str(value or "")).strip()
    return clean if clean else fallback


def _review_text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return clean_review_value(_text(value, ""), fallback)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _markdown_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return _text(value, fallback).replace("|", "\\|").replace("\n", "<br>")


def _plain_text_value(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    return " ".join(_text(value, fallback).replace("\r", "\n").split())


def _compact(values: list[Any], fallback: str = "NOT_AVAILABLE") -> str:
    clean_values: list[str] = []
    for value in values:
        clean = _review_text(value, "")
        if clean and clean not in clean_values:
            clean_values.append(clean)
    return "; ".join(clean_values) if clean_values else fallback


def _first_present(source: Mapping[str, Any], keys: tuple[str, ...], fallback: str = "NOT_AVAILABLE") -> str:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}) and not is_placeholder_review_value(value):
            return _review_text(value, fallback)
    return fallback


def _candidate_expression_systems(case_context: Mapping[str, Any], project: Mapping[str, Any]) -> list[str]:
    raw_values: list[Any] = []
    for source in (case_context, project):
        for key in (
            "candidate_expression_systems",
            "expression_systems",
            "candidate_hosts",
            "host_candidates",
            "host_options",
        ):
            raw_values.extend(_as_list(source.get(key)))
    if not raw_values:
        raw_values.extend(
            value
            for value in (
                project.get("host"),
                project.get("chassis"),
                project.get("organism"),
                project.get("host_context"),
            )
            if value not in (None, "", [], {})
        )
    systems = [
        _review_text(value, "")
        for value in raw_values
        if _review_text(value, "") and not is_placeholder_review_value(value)
    ]
    deduped: list[str] = []
    for system in systems:
        if system not in deduped:
            deduped.append(system)
    return deduped or ["Candidate expression systems not yet selected; record options for company review."]


def _case_objective(case_context: Mapping[str, Any], project: Mapping[str, Any]) -> str:
    return _first_present(
        case_context,
        ("case_objective", "objective", "validation_objective"),
        _first_present(
            project,
            ("case_objective", "objective", "description", "project_description", "review_notes", "notes"),
            "Prepare one documented design case for teacher/company feasibility review before any external experimental work.",
        ),
    )


def _candidate_target(case_context: Mapping[str, Any], project: Mapping[str, Any]) -> str:
    return _first_present(
        case_context,
        ("candidate_target", "target", "target_protein", "target_product", "target_pathway"),
        _first_present(
            project,
            (
                "target_protein",
                "protein_target",
                "target_product",
                "target_pathway",
                "name",
                "project_name",
            ),
            "Candidate target not recorded; record target protein, product, or pathway before company review.",
        ),
    )


def _construct_design_summary(
    case_context: Mapping[str, Any],
    project: Mapping[str, Any],
    construct_component_queue: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _mapping(construct_component_queue.get("summary"))
    return {
        "title": "Construct design summary",
        "construct_label": _first_present(
            case_context,
            ("construct_label", "construct_name"),
            _first_present(project, ("construct_label", "construct_name", "name", "project_name"), "Construct label not recorded"),
        ),
        "summary_note": _first_present(
            case_context,
            ("construct_summary", "construct_design_summary"),
            _first_present(project, ("construct_summary", "construct_design_summary"), "Construct summary not recorded"),
        ),
        "component_rows_reviewed": _int(summary.get("total_component_rows")),
        "manual_follow_up_items": _int(summary.get("rows_needing_manual_follow_up")),
        "boundary_note": (
            "Construct design summary is read-only documentation context; it does not decide downstream-use state."
        ),
    }


def _component_evidence_summary(construct_component_queue: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(construct_component_queue.get("summary"))
    return {
        "title": "Component evidence/provenance summary",
        "component_rows_reviewed": _int(summary.get("total_component_rows")),
        "source_reference_context_rows": _int(summary.get("rows_with_source_reference_context")),
        "missing_source_reference_context_rows": _int(summary.get("rows_missing_source_reference_context")),
        "record_review_status_rows": _int(summary.get("rows_with_review_metadata_status")),
        "review_note_rows": _int(summary.get("rows_with_review_note")),
        "manual_follow_up_items": _int(summary.get("rows_needing_manual_follow_up")),
        "boundary_note": (
            "Component evidence/provenance summary records existing source and review context only."
        ),
    }


def _codon_status_summary(codon_status: Mapping[str, Any]) -> dict[str, Any]:
    if not codon_status:
        return {
            "title": "Codon usage / optimization status summary",
            "status": "NOT_SUPPLIED",
            "host_context": "NOT_AVAILABLE",
            "preview_provider": "NOT_AVAILABLE",
            "sequence_change_status": "No codon usage preview status was supplied.",
            "warning_count": 0,
            "manual_review_cue": "Manual/company review remains required before downstream biological decisions.",
            "boundary_note": (
                "Codon usage status is documentation context only; no codon rewriting is performed by this package."
            ),
        }
    changed = bool(codon_status.get("changed") or codon_status.get("sequence_changed"))
    warnings = _rows(codon_status.get("warnings"))
    if not warnings:
        warnings = [
            {"warning": value}
            for value in _as_list(codon_status.get("warning_list"))
            if _review_text(value, "")
        ]
    return {
        "title": "Codon usage / optimization status summary",
        "status": _review_text(codon_status.get("status") or codon_status.get("success"), "RECORDED"),
        "host_context": _review_text(codon_status.get("host") or codon_status.get("host_context"), "NOT_AVAILABLE"),
        "preview_provider": _review_text(
            codon_status.get("preview_provider") or codon_status.get("source") or codon_status.get("origin_page"),
            "NOT_AVAILABLE",
        ),
        "sequence_change_status": (
            "Preview sequence differs from the input record; review manually."
            if changed
            else "No preview sequence change is recorded in the supplied status."
        ),
        "warning_count": _int(codon_status.get("warning_count") if "warning_count" in codon_status else len(warnings)),
        "manual_review_cue": _review_text(
            codon_status.get("manual_review_cue"),
            "Manual/company review remains required before downstream biological decisions.",
        ),
        "boundary_note": (
            "Codon usage status is documentation context only; this package does not perform codon rewriting."
        ),
    }


def _conservation_review_summary(construct_component_queue: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(construct_component_queue.get("summary"))
    return {
        "title": "Component conservation review summary",
        "conservation_context_rows": _int(summary.get("rows_with_conservation_review_context")),
        "conservation_follow_up_rows": _int(summary.get("rows_needing_conservation_follow_up")),
        "boundary_note": (
            "Component conservation review is manual documentation readback only; no BLAST, MSA, "
            "conserved-domain analysis, or automatic conservation classification is run here."
        ),
    }


def _review_gap_rows(
    construct_component_queue: Mapping[str, Any],
    handoff_preview: Mapping[str, Any],
    case_context: Mapping[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _rows(construct_component_queue.get("rows")):
        rows.append(
            {
                "source_surface": "Expression construct documentation follow-up",
                "item_label": _review_text(
                    row.get("Component label") or row.get("Cassette label") or row.get("Construct label"),
                    "Construct component row",
                ),
                "issue_type": _review_text(row.get("Issue type"), "Documentation follow-up"),
                "manual_follow_up_note": _review_text(
                    row.get("Manual follow-up note"),
                    "Manual documentation follow-up remains visible.",
                ),
            }
        )
    for row in _rows(handoff_preview.get("manual_follow_up_queue")):
        rows.append(
            {
                "source_surface": _review_text(row.get("source_surface"), "Project handoff review"),
                "item_label": _review_text(row.get("item_label"), "Documentation review item"),
                "issue_type": _review_text(row.get("issue_type"), "Documentation follow-up"),
                "manual_follow_up_note": _review_text(
                    row.get("manual_follow_up_note"),
                    "Manual documentation follow-up remains visible.",
                ),
            }
        )
    for row in _rows(case_context.get("review_gaps")):
        rows.append(
            {
                "source_surface": _review_text(row.get("source_surface"), "Validation case package"),
                "item_label": _review_text(row.get("item_label") or row.get("label"), "Manual follow-up item"),
                "issue_type": _review_text(row.get("issue_type") or row.get("issue"), "Manual follow-up"),
                "manual_follow_up_note": _review_text(
                    row.get("manual_follow_up_note") or row.get("note"),
                    "Record expert/company follow-up.",
                ),
            }
        )
    if not rows:
        rows.append(
            {
                "source_surface": "Validation case package",
                "item_label": "Manual review planning",
                "issue_type": "No review gaps supplied",
                "manual_follow_up_note": "Confirm objective, target, candidate systems, source evidence, codon status, and conservation review with expert/company reviewers.",
            }
        )
    return rows


def _package_identity(package: Mapping[str, Any], normalized_content: str) -> dict[str, Any]:
    supplied_identity = _mapping(package.get("package_identity"))
    checksum = hashlib.md5(normalized_content.encode("utf-8")).hexdigest()
    return {
        "software_name": _review_text(supplied_identity.get("software_name"), "BioDesign Studio"),
        "package_title": PACKAGE_TITLE,
        "git_tag": _review_text(supplied_identity.get("git_tag"), "NOT_RECORDED"),
        "commit": _review_text(supplied_identity.get("commit"), "NOT_RECORDED"),
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "snapshot_checksum": checksum,
        "snapshot_id": f"{CHECKSUM_ALGORITHM.lower()}:{checksum}",
        "identity_boundary_note": (
            "MD5 is for package-preview matching only, not a security signature or certification."
        ),
    }


def _format_qr_payload(identity: Mapping[str, Any], package: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            QR_PAYLOAD_HEADER,
            f"Package title: {_plain_text_value(identity.get('package_title'), PACKAGE_TITLE)}",
            f"Case target: {_plain_text_value(package.get('candidate_target'))}",
            f"Snapshot ID: {_plain_text_value(identity.get('snapshot_id'))}",
            f"Checksum algorithm: {_plain_text_value(identity.get('checksum_algorithm'), CHECKSUM_ALGORITHM)}",
            f"MD5 preview checksum: {_plain_text_value(identity.get('snapshot_checksum'))}",
            f"Git tag: {_plain_text_value(identity.get('git_tag'))}",
            f"Commit: {_plain_text_value(identity.get('commit'))}",
            "Boundary: Documentation-only feasibility review package.",
            "Boundary: Not a wet-lab protocol.",
            "Boundary: Does not replace expert/company review.",
        ]
    )


def format_validation_case_package_markdown(package: Mapping[str, Any]) -> str:
    construct = _mapping(package.get("construct_design_summary"))
    evidence = _mapping(package.get("component_evidence_provenance_summary"))
    codon = _mapping(package.get("codon_usage_optimization_status_summary"))
    conservation = _mapping(package.get("component_conservation_review_summary"))
    identity = _mapping(package.get("software_package_identity"))
    lines = [
        f"## {PACKAGE_TITLE}",
        f"- {PACKAGE_SUBTITLE}",
        f"- Case objective: {_markdown_value(package.get('case_objective'))}",
        f"- Candidate target protein/product/pathway: {_markdown_value(package.get('candidate_target'))}",
        "- Candidate expression systems: "
        + ", ".join(_markdown_value(system) for system in package.get("candidate_expression_systems") or []),
        "",
        "### Construct design summary",
        f"- Construct label: {_markdown_value(construct.get('construct_label'))}",
        f"- Summary note: {_markdown_value(construct.get('summary_note'))}",
        f"- Component rows reviewed: {_int(construct.get('component_rows_reviewed'))}",
        f"- Manual follow-up items: {_int(construct.get('manual_follow_up_items'))}",
        f"- Boundary: {_markdown_value(construct.get('boundary_note'))}",
        "",
        "### Component evidence/provenance summary",
        f"- Component rows reviewed: {_int(evidence.get('component_rows_reviewed'))}",
        f"- Source/reference context rows: {_int(evidence.get('source_reference_context_rows'))}",
        f"- Missing source/reference context rows: {_int(evidence.get('missing_source_reference_context_rows'))}",
        f"- Record review status rows: {_int(evidence.get('record_review_status_rows'))}",
        f"- Review note rows: {_int(evidence.get('review_note_rows'))}",
        f"- Manual follow-up items: {_int(evidence.get('manual_follow_up_items'))}",
        f"- Boundary: {_markdown_value(evidence.get('boundary_note'))}",
        "",
        "### Codon usage / optimization status summary",
        f"- Status: {_markdown_value(codon.get('status'))}",
        f"- Host context: {_markdown_value(codon.get('host_context'))}",
        f"- Preview provider: {_markdown_value(codon.get('preview_provider'))}",
        f"- Sequence change status: {_markdown_value(codon.get('sequence_change_status'))}",
        f"- Warning count: {_int(codon.get('warning_count'))}",
        f"- Manual review cue: {_markdown_value(codon.get('manual_review_cue'))}",
        f"- Boundary: {_markdown_value(codon.get('boundary_note'))}",
        "",
        "### Component conservation review summary",
        f"- Conservation context rows: {_int(conservation.get('conservation_context_rows'))}",
        f"- Conservation follow-up rows: {_int(conservation.get('conservation_follow_up_rows'))}",
        f"- Boundary: {_markdown_value(conservation.get('boundary_note'))}",
        "",
        "### Review gaps / manual follow-up list",
        "| Source surface | Item label | Issue type | Manual follow-up note |",
        "| --- | --- | --- | --- |",
    ]
    for row in _rows(package.get("review_gaps_manual_follow_up_list")):
        lines.append(
            "| "
            + " | ".join(
                _markdown_value(row.get(key))
                for key in ("source_surface", "item_label", "issue_type", "manual_follow_up_note")
            )
            + " |"
        )
    lines += [
        "",
        "### Company feasibility feedback placeholder",
        f"- {_markdown_value(package.get('company_feasibility_feedback_placeholder'))}",
        "",
        "### Experiment status placeholder",
        f"- {_markdown_value(package.get('experiment_status_placeholder'))}",
        "",
        "### Result summary placeholder",
        f"- {_markdown_value(package.get('result_summary_placeholder'))}",
        "",
        "### Software/package identity",
        f"- Software: {_markdown_value(identity.get('software_name'))}",
        f"- Git tag: {_markdown_value(identity.get('git_tag'))}",
        f"- Commit: {_markdown_value(identity.get('commit'))}",
        f"- Snapshot ID: {_markdown_value(identity.get('snapshot_id'))}",
        f"- Checksum algorithm: {_markdown_value(identity.get('checksum_algorithm'))}",
        f"- MD5 preview checksum: {_markdown_value(identity.get('snapshot_checksum'))}",
        f"- Boundary: {_markdown_value(identity.get('identity_boundary_note'))}",
        "",
        "### Boundary notes",
    ]
    for note in package.get("boundary_notes") or []:
        lines.append(f"- {_markdown_value(note)}")
    return "\n".join(lines)


def format_validation_case_package_plain_text(package: Mapping[str, Any]) -> str:
    lines = [
        PACKAGE_TITLE,
        PACKAGE_SUBTITLE,
        f"Case objective: {_plain_text_value(package.get('case_objective'))}",
        f"Candidate target protein/product/pathway: {_plain_text_value(package.get('candidate_target'))}",
        "Candidate expression systems: "
        + ", ".join(_plain_text_value(system) for system in package.get("candidate_expression_systems") or []),
        f"Review gap count: {len(_rows(package.get('review_gaps_manual_follow_up_list')))}",
        f"Company feasibility feedback placeholder: {_plain_text_value(package.get('company_feasibility_feedback_placeholder'))}",
        f"Experiment status placeholder: {_plain_text_value(package.get('experiment_status_placeholder'))}",
        f"Result summary placeholder: {_plain_text_value(package.get('result_summary_placeholder'))}",
        f"Snapshot ID: {_plain_text_value(_mapping(package.get('software_package_identity')).get('snapshot_id'))}",
        f"MD5 preview checksum: {_plain_text_value(_mapping(package.get('software_package_identity')).get('snapshot_checksum'))}",
        "Boundary notes:",
    ]
    for note in package.get("boundary_notes") or []:
        lines.append(f"- {_plain_text_value(note)}")
    return "\n".join(lines)


def build_validation_case_package(
    *,
    case_context: Mapping[str, Any] | None = None,
    project: Mapping[str, Any] | None = None,
    construct_component_queue: Mapping[str, Any] | None = None,
    handoff_preview: Mapping[str, Any] | None = None,
    codon_status: Mapping[str, Any] | None = None,
    package_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic documentation-only validation case package preview."""
    case_context = _mapping(case_context)
    project = _mapping(project)
    construct_component_queue = _mapping(construct_component_queue)
    handoff_preview = _mapping(handoff_preview)
    codon_status = _mapping(codon_status)

    package = {
        "title": PACKAGE_TITLE,
        "subtitle": PACKAGE_SUBTITLE,
        "status": "AVAILABLE",
        "case_objective": _case_objective(case_context, project),
        "candidate_target": _candidate_target(case_context, project),
        "candidate_expression_systems": _candidate_expression_systems(case_context, project),
        "construct_design_summary": _construct_design_summary(
            case_context,
            project,
            construct_component_queue,
        ),
        "component_evidence_provenance_summary": _component_evidence_summary(construct_component_queue),
        "codon_usage_optimization_status_summary": _codon_status_summary(codon_status),
        "component_conservation_review_summary": _conservation_review_summary(construct_component_queue),
        "review_gaps_manual_follow_up_list": _review_gap_rows(
            construct_component_queue,
            handoff_preview,
            case_context,
        ),
        "company_feasibility_feedback_placeholder": _review_text(
            case_context.get("company_feasibility_feedback_placeholder"),
            DEFAULT_COMPANY_FEEDBACK_PLACEHOLDER,
        ),
        "experiment_status_placeholder": _review_text(
            case_context.get("experiment_status_placeholder"),
            DEFAULT_EXPERIMENT_STATUS_PLACEHOLDER,
        ),
        "result_summary_placeholder": _review_text(
            case_context.get("result_summary_placeholder"),
            DEFAULT_RESULT_SUMMARY_PLACEHOLDER,
        ),
        "package_identity": dict(package_identity or {}),
        "boundary_notes": BOUNDARY_NOTES[:],
    }
    package = normalize_generated_output_claims(package)
    base_markdown = format_validation_case_package_markdown(package)
    identity = _package_identity(package, base_markdown)
    package["software_package_identity"] = identity
    package["qr_verification_payload_text"] = _format_qr_payload(identity, package)
    package["markdown"] = format_validation_case_package_markdown(package)
    package["plain_text"] = format_validation_case_package_plain_text(package)
    package = normalize_generated_output_claims(package)
    assert_no_misleading_generated_claims(package, context="validation case package")

    lower_output = str(package).lower()
    unsafe_patterns = (
        r"\bguaranteed\s+expression\b",
        r"\brecommended\s+expression\s+system\b",
        r"\bselects?\s+the\s+best\s+expression\s+system\b",
        r"\bautomatically\s+optimizes?\b",
        r"\bautomatically\s+classifies?\s+conservation\b",
    )
    for pattern in unsafe_patterns:
        if re.search(pattern, lower_output):
            raise ValueError("Misleading validation case package boundary wording detected.")
    return package
