from __future__ import annotations

from typing import Any

from services.validation_summary_service import PRIMER_HIGH_RISK_CODE, PRIMER_REVIEW_CODE, PRIMER_UNAVAILABLE_CODE


def build_export_recommendation(
    validation_results: list[dict[str, Any]],
    primers: list[dict[str, Any]],
    seq: str,
    validation_complete: bool | None = None,
) -> dict[str, Any]:
    """Build the final export recommendation from validation-first risk signals."""
    issues = [item for item in (validation_results or []) if isinstance(item, dict)]
    primer_rows = [item for item in (primers or []) if isinstance(item, dict)]

    critical_issues = [item for item in issues if item.get("severity") == "critical"]
    warning_issues = [item for item in issues if item.get("severity") == "warning"]
    primer_high_risk_issues = [item for item in issues if item.get("code") == PRIMER_HIGH_RISK_CODE]
    primer_review_issues = [item for item in issues if item.get("code") == PRIMER_REVIEW_CODE]
    primer_unavailable_issues = [item for item in issues if item.get("code") == PRIMER_UNAVAILABLE_CODE]

    affected_fragments: list[str] = []
    primer_high_risk_count = 0
    primer_review_count = 0
    for primer in primer_rows:
        fragment = str(primer.get("Fragment Name") or "").strip()
        grade = str(primer.get("Quality Grade") or "").strip()
        if grade == "Not Recommended":
            primer_high_risk_count += 1
            if fragment:
                affected_fragments.append(fragment)
        elif grade == "Usable with Risk":
            primer_review_count += 1
            if fragment:
                affected_fragments.append(fragment)

    affected_fragments = list(dict.fromkeys(affected_fragments))
    has_sequence = bool(seq)
    validation_complete = bool(issues) if validation_complete is None else bool(validation_complete)
    has_critical = bool(critical_issues)
    has_primer_high_risk = bool(primer_high_risk_issues) or primer_high_risk_count > 0
    has_review_required = bool(primer_review_issues) or bool(primer_unavailable_issues) or bool(warning_issues) or primer_review_count > 0
    primer_action_required_count = primer_high_risk_count + primer_review_count

    if not has_sequence or not validation_complete or has_critical or has_primer_high_risk:
        recommendation = "Review blocked by unresolved risk signals"
        tone = "warn"
        if not has_sequence:
            conclusion = "No final construct sequence is available yet, so this design is not ready for documentation export review."
            action = "Complete upstream sequence and frame generation first, then use the Step 6 export output for documentation review."
        elif not validation_complete:
            conclusion = "Validation is not complete yet, so the export files should remain documentation-only review records."
            action = "Finish Step 5 validation before using the export output for documentation review."
        elif has_critical:
            conclusion = "Blocking validation issues are still present, so documentation export review is blocked by unresolved risk signals."
            action = "Return to Step 5, resolve the critical validation issues, and then review export records again."
        else:
            conclusion = "Step 5 carried forward high-risk primer results, so documentation export review is blocked by unresolved risk signals."
            action = "Return to Step 4, review the high-risk primers, and rerun Step 5 validation afterward."
    elif has_review_required:
        recommendation = "Export with Review Required"
        tone = "info"
        conclusion = "Review-level risk signals are still present. Export files can be generated as documentation-only records while review remains open."
        if primer_unavailable_issues:
            action = "Review the unavailable primer-design status carried into Step 5 before using export files as documentation records."
        elif primer_review_issues:
            action = "Review the primer-risk summary carried into Step 5 first. If needed, return to Step 4 to improve primer quality."
        else:
            action = "Review the warning-level validation issues in Step 5 before using the export files as documentation records."
    else:
        recommendation = "Documentation Export Available"
        tone = "ready"
        conclusion = "Current documentation checks are complete, the active primer option is acceptable, and no recorded review blockers remain in this workspace record. Documentation export records are available."
        action = "Continue exporting FASTA, GenBank, the report, and the construct/cassette map preview PNG for documentation review."

    return {
        "recommendation": recommendation,
        "tone": tone,
        "conclusion": conclusion,
        "action": action,
        "critical_count": len(critical_issues),
        "warning_count": len(warning_issues),
        "primer_high_risk_count": primer_high_risk_count,
        "primer_review_count": primer_review_count,
        "primer_action_required_count": primer_action_required_count,
        "affected_fragments": affected_fragments,
    }
