from __future__ import annotations

from typing import Any

from core.expression_frame_builder import validate_frame

PRIMER_REVIEW_CODE = "PRIMER_REVIEW_REQUIRED"
PRIMER_HIGH_RISK_CODE = "PRIMER_HIGH_RISK"


def _build_primer_risk_summary(primers: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "recommended": 0,
        "usable_with_risk": 0,
        "not_recommended": 0,
        "affected_fragments": [],
        "top_reasons": [],
        "issue": None,
    }
    if not primers:
        return summary

    affected_fragments: list[str] = []
    reason_counts: dict[str, int] = {}

    for primer in primers:
        grade = str(primer.get("Quality Grade") or "").strip()
        fragment = str(primer.get("Fragment Name") or "Unnamed fragment").strip() or "Unnamed fragment"
        reasons = primer.get("Quality Reasons") or primer.get("Warnings") or []

        if grade == "Recommended":
            summary["recommended"] += 1
        elif grade == "Not Recommended":
            summary["not_recommended"] += 1
            affected_fragments.append(fragment)
        else:
            summary["usable_with_risk"] += 1
            affected_fragments.append(fragment)

        for reason in reasons:
            text = str(reason).strip()
            if text:
                reason_counts[text] = reason_counts.get(text, 0) + 1

    summary["affected_fragments"] = list(dict.fromkeys(affected_fragments))
    summary["top_reasons"] = [
        reason for reason, _count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:3]
    ]

    fragments = ", ".join(summary["affected_fragments"][:4]) or "one or more fragments"
    if len(summary["affected_fragments"]) > 4:
        fragments += f", plus {len(summary['affected_fragments']) - 4} more"
    reasons_text = "; ".join(summary["top_reasons"])

    if summary["not_recommended"]:
        summary["issue"] = {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pair(s) detected",
            "why": (
                f"Step 4 marked {summary['not_recommended']} primer pair(s) as Not Recommended across {fragments}. "
                f"{reasons_text or 'High-risk primer interaction or critical metric drift was reported.'}"
            ),
            "fix": "Return to Step 4 and review primer quality before export.",
        }
    elif summary["usable_with_risk"]:
        summary["issue"] = {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review recommended",
            "why": (
                f"Step 4 marked {summary['usable_with_risk']} primer pair(s) as Usable with Risk across {fragments}. "
                f"{reasons_text or 'Primer metrics are outside the preferred range.'}"
            ),
            "fix": "Review primer quality before export or return to Step 4 for adjustments.",
        }

    return summary


def merge_validation_with_primer_risk(base_issues: list[dict[str, Any]], primers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary = _build_primer_risk_summary(primers)
    merged = [
        issue for issue in (base_issues or [])
        if issue.get("code") not in {PRIMER_REVIEW_CODE, PRIMER_HIGH_RISK_CODE}
    ]
    primer_issue = summary.get("issue")
    if not primer_issue:
        return merged, summary

    pass_idx = next((idx for idx, issue in enumerate(merged) if issue.get("code") == "PASS"), None)
    if pass_idx is None:
        merged.append(primer_issue)
    else:
        merged.insert(pass_idx, primer_issue)
    return merged, summary


def run_validation_report(frame: dict[str, Any], primers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    safe_frame = frame if isinstance(frame, dict) else {}
    safe_primers = primers if isinstance(primers, list) else []

    issues = validate_frame(safe_frame)
    merged_issues, primer_summary = merge_validation_with_primer_risk(issues, safe_primers)

    return {
        "issues": merged_issues,
        "primer_summary": primer_summary,
    }
