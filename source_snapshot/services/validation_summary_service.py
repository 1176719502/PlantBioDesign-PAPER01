from __future__ import annotations

from collections import Counter
from typing import Any


PRIMER_REVIEW_CODE = "PRIMER_REVIEW_REQUIRED"
PRIMER_HIGH_RISK_CODE = "PRIMER_HIGH_RISK"
PRIMER_UNAVAILABLE_CODE = "PRIMER_DESIGN_UNAVAILABLE"


DEFAULT_VALIDATION_COPY = {
    "blocking_detected_title": "Blocking issues detected",
    "high_risk_review_title": "Validation complete — high-risk primers still require review",
    "review_required_title": "Validation complete — manual review recommended",
    "validation_passed_title": "Documentation checks completed",
}


def build_primer_risk_summary(primers: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize Step 4 primer quality for Step 5/report/export consumers."""
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
    reason_counter: Counter[str] = Counter()

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
                reason_counter[text] += 1

    summary["affected_fragments"] = list(dict.fromkeys(affected_fragments))
    summary["top_reasons"] = [reason for reason, _ in reason_counter.most_common(3)]

    fragments = ", ".join(summary["affected_fragments"][:4]) or "one or more fragments"
    if len(summary["affected_fragments"]) > 4:
        fragments += f", plus {len(summary['affected_fragments']) - 4} more"
    reasons = "; ".join(summary["top_reasons"])

    if summary["not_recommended"]:
        summary["issue"] = {
            "severity": "warning",
            "code": PRIMER_HIGH_RISK_CODE,
            "title": "High-risk primer pairs detected",
            "why": (
                f"Step 4 marked {summary['not_recommended']} primer pair(s) as Not Recommended, affecting {fragments}. "
                f"{reasons or 'The system reported severe primer interactions or major metric deviations.'}"
            ),
            "fix": "Return to Step 4 and review the primer design before export. Export can still proceed, but this result should not be treated as a full pass.",
        }
    elif summary["usable_with_risk"]:
        summary["issue"] = {
            "severity": "warning",
            "code": PRIMER_REVIEW_CODE,
            "title": "Primer quality review is recommended",
            "why": (
                f"Step 4 marked {summary['usable_with_risk']} primer pair(s) as Usable with Risk, affecting {fragments}. "
                f"{reasons or 'Some primer metrics are outside the recommended range.'}"
            ),
            "fix": "Review the primer set before export. If needed, return to Step 4 and optimize overlap, Tm, GC, or primer interaction metrics.",
        }

    return summary


def build_primer_unavailable_issue(ds: Any) -> dict[str, Any] | None:
    """Return a Step 5 warning when Step 4 recorded unavailable primer design."""
    if str(getattr(ds, "primer_design_status", "") or "").strip().lower() != "unavailable":
        return None
    if getattr(ds, "primer_backend_available", None) is not False:
        return None
    return {
        "severity": "warning",
        "code": PRIMER_UNAVAILABLE_CODE,
        "title": "Primer candidate generation not enabled",
        "why": "Step 4 recorded cassette boundary review context only; no primer candidate rows are recorded in this build.",
        "fix": "Continue documentation-only review without treating primer status as generated.",
    }



def merge_validation_with_primer_risk(base_issues: list[dict[str, Any]], primers: list[dict[str, Any]], ds: Any | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge biological validation with a single primer summary issue."""
    summary = build_primer_risk_summary(primers)
    merged = [
        issue for issue in (base_issues or [])
        if issue.get("code") not in {PRIMER_REVIEW_CODE, PRIMER_HIGH_RISK_CODE, PRIMER_UNAVAILABLE_CODE}
    ]
    unavailable_issue = build_primer_unavailable_issue(ds) if ds is not None else None
    if unavailable_issue:
        merged = [issue for issue in merged if issue.get("code") != "PASS"]
        merged.append(unavailable_issue)
        summary["issue"] = unavailable_issue
        summary["primer_design_status"] = "unavailable"
        return merged, summary

    primer_issue = summary.get("issue")
    if not primer_issue:
        return merged, summary

    merged = [issue for issue in merged if issue.get("code") != "PASS"]
    merged.append(primer_issue)
    return merged, summary



def build_validation_run_state(
    ds: Any,
    task_status: str | None = None,
    task_error: str | None = None,
) -> dict[str, Any]:
    """Resolve the current Step 5 validation run state for export/report consumers."""
    issues = [
        issue for issue in (getattr(ds, "validation_results", []) or [])
        if isinstance(issue, dict)
    ]
    critical_count = sum(1 for issue in issues if issue.get("severity") == "critical")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    info_count = sum(1 for issue in issues if issue.get("severity") == "info")

    try:
        is_stale = bool(ds.validation_is_stale())
    except Exception:
        is_stale = False

    has_context_signature = bool(str(getattr(ds, "validation_context_signature", "") or "").strip())
    if has_context_signature and not is_stale:
        try:
            is_stale = getattr(ds, "validation_context_signature") != ds.current_validation_context_signature()
        except Exception:
            is_stale = False
    has_result_rows = bool(issues)
    has_completed_result = (has_result_rows or has_context_signature) and not is_stale

    normalized_task_status = str(task_status or "").strip().lower()
    normalized_task_error = str(task_error or "").strip()
    running_statuses = {"queued", "started", "running"}
    failed_statuses = {"failed", "not_found", "unavailable"}

    is_running = normalized_task_status in running_statuses and not has_completed_result
    is_failed = (
        normalized_task_status in failed_statuses or bool(normalized_task_error)
    ) and not has_completed_result

    if is_stale:
        status = "stale"
    elif has_completed_result:
        if critical_count:
            status = "completed_blocked"
        elif warning_count:
            status = "completed_review"
        else:
            status = "completed_passed"
    elif is_failed:
        status = "failed"
    elif is_running:
        status = "running"
    else:
        status = "not_run"

    return {
        "status": status,
        "is_complete": status.startswith("completed_"),
        "is_running": status == "running",
        "is_failed": status == "failed",
        "is_stale": status == "stale",
        "issues": issues,
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
    }


def build_validation_conclusion(issues: list[dict[str, Any]], copy: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the top-level validation conclusion for page/report/export consumers."""
    ui_copy = {**DEFAULT_VALIDATION_COPY, **(copy or {})}
    issues = [issue for issue in (issues or []) if isinstance(issue, dict)]
    criticals = [issue for issue in issues if issue.get("severity") == "critical"]
    warnings = [issue for issue in issues if issue.get("severity") == "warning"]
    infos = [issue for issue in issues if issue.get("severity") == "info"]
    has_primer_high_risk = any(issue.get("code") == PRIMER_HIGH_RISK_CODE for issue in issues)
    has_primer_unavailable = any(issue.get("code") == PRIMER_UNAVAILABLE_CODE for issue in issues)

    if criticals:
        return {
            "status": "blocking",
            "title": ui_copy["blocking_detected_title"],
            "summary": f"Detected {len(criticals)} critical issue(s) that must be resolved before export.",
            "tone": "warn",
            "critical_count": len(criticals),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "has_primer_high_risk": has_primer_high_risk,
        }
    if has_primer_high_risk:
        return {
            "status": "high_risk_primer_review",
            "title": ui_copy["high_risk_review_title"],
            "summary": "No blocking biological issue was detected, but Step 4 reported high-risk primer pairs that must be reviewed before export.",
            "tone": "warn",
            "critical_count": len(criticals),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "has_primer_high_risk": has_primer_high_risk,
        }
    if has_primer_unavailable:
        return {
            "status": "primer_unavailable_review",
            "title": ui_copy["review_required_title"],
            "summary": "Primer design is unavailable in this environment, so Step 5 keeps primer status in documentation-only review.",
            "tone": "info",
            "critical_count": len(criticals),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "has_primer_high_risk": has_primer_high_risk,
        }
    if warnings:
        return {
            "status": "review_required",
            "title": ui_copy["review_required_title"],
            "summary": f"Validation completed with {len(warnings)} warning(s); manual review is recommended before export.",
            "tone": "info",
            "critical_count": len(criticals),
            "warning_count": len(warnings),
            "info_count": len(infos),
            "has_primer_high_risk": has_primer_high_risk,
        }
    return {
        "status": "passed",
        "title": ui_copy["validation_passed_title"],
        "summary": "No critical or warning-level issue was detected; the current construct can proceed to export.",
        "tone": "ready",
        "critical_count": len(criticals),
        "warning_count": len(warnings),
        "info_count": len(infos),
        "has_primer_high_risk": has_primer_high_risk,
    }
