from __future__ import annotations

from typing import Any, Dict, List


READINESS_AVAILABLE_FOR_REVIEW = "Available for review"
READINESS_NEEDS_REVIEW = "Needs Review"
READINESS_BLOCKED = "Blocked"

WARNING_LEVEL_NONE = "none"
WARNING_LEVEL_WARNING = "warning"
WARNING_LEVEL_BLOCKER = "blocker"


def _stored_step4_plan_summary(ds) -> Dict[str, Any]:
    summary = getattr(ds, "step4_plan_summary", None)
    return summary if isinstance(summary, dict) else {}


def _selected_structured_result(plan: Dict[str, Any]) -> Dict[str, Any]:
    structured_results = plan.get("structured_results") or []
    selected_index = int(plan.get("selected_result_index", 0) or 0)
    if not isinstance(structured_results, list) or not structured_results:
        return {}

    safe_index = max(0, min(len(structured_results) - 1, selected_index))
    selected_result = structured_results[safe_index]
    return selected_result if isinstance(selected_result, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _nested_text(mapping: Dict[str, Any], *keys: str) -> str:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _first_text(current)


def _build_vector_backbone_metadata(frame: Dict[str, Any], plan: Dict[str, Any], selected_result: Dict[str, Any]) -> Dict[str, str]:
    vector_info = frame.get("vector") if isinstance(frame.get("vector"), dict) else {}
    backbone_info = frame.get("backbone") if isinstance(frame.get("backbone"), dict) else {}
    plan_vector_info = plan.get("vector") if isinstance(plan.get("vector"), dict) else {}
    plan_backbone_info = plan.get("backbone") if isinstance(plan.get("backbone"), dict) else {}
    selected_vector_info = selected_result.get("vector") if isinstance(selected_result.get("vector"), dict) else {}
    selected_backbone_info = selected_result.get("backbone") if isinstance(selected_result.get("backbone"), dict) else {}

    name = _first_text(
        _nested_text(frame, "vector", "name"),
        _nested_text(frame, "backbone", "name"),
        frame.get("vector_name"),
        frame.get("backbone_name"),
        frame.get("vector_suggestion"),
        frame.get("vector") if not isinstance(frame.get("vector"), dict) else "",
        frame.get("backbone") if not isinstance(frame.get("backbone"), dict) else "",
        _nested_text(plan, "vector", "name"),
        _nested_text(plan, "backbone", "name"),
        plan.get("vector_name"),
        plan.get("backbone_name"),
        plan.get("vector_suggestion"),
        plan.get("vector_backbone"),
        _nested_text(selected_result, "vector", "name"),
        _nested_text(selected_result, "backbone", "name"),
        selected_result.get("vector_name"),
        selected_result.get("backbone_name"),
        selected_result.get("vector_suggestion"),
        selected_result.get("vector_backbone"),
    )
    source = _first_text(
        vector_info.get("source"),
        backbone_info.get("source"),
        frame.get("vector_source"),
        frame.get("backbone_source"),
        plan_vector_info.get("source"),
        plan_backbone_info.get("source"),
        plan.get("vector_source"),
        plan.get("backbone_source"),
        selected_vector_info.get("source"),
        selected_backbone_info.get("source"),
        selected_result.get("vector_source"),
        selected_result.get("backbone_source"),
    )
    return {
        "vector_backbone_name": name,
        "backbone_source": source,
        "vector_backbone": name,
    }


def _build_readiness(
    primer_count: int,
    warning_count: int,
    is_stale: bool,
    grade_counts: Dict[str, int] | None = None,
) -> Dict[str, Any]:
    reasons: List[str] = []
    grade_counts = grade_counts or {}

    if primer_count <= 0:
        reasons.append("Primer results are missing.")
        return {
            "readiness_status": READINESS_BLOCKED,
            "readiness_reasons": reasons,
            "warning_level": WARNING_LEVEL_BLOCKER,
        }

    if is_stale:
        reasons.append("Primer results are stale relative to the current design context.")
        return {
            "readiness_status": READINESS_BLOCKED,
            "readiness_reasons": reasons,
            "warning_level": WARNING_LEVEL_BLOCKER,
        }

    if grade_counts.get("Not Recommended", 0) > 0:
        reasons.append("The active primer option is Not Recommended and requires manual review before any external use beyond documentation.")
        return {
            "readiness_status": READINESS_BLOCKED,
            "readiness_reasons": reasons,
            "warning_level": WARNING_LEVEL_BLOCKER,
        }

    if grade_counts.get("Usable with Risk", 0) > 0:
        reasons.append("The active primer option is Usable with Risk and needs manual review before any external use beyond documentation.")
        return {
            "readiness_status": READINESS_NEEDS_REVIEW,
            "readiness_reasons": reasons,
            "warning_level": WARNING_LEVEL_WARNING,
        }

    if warning_count > 0:
        reasons.append("Primer warnings are present and should be reviewed before continuing.")
        return {
            "readiness_status": READINESS_NEEDS_REVIEW,
            "readiness_reasons": reasons,
            "warning_level": WARNING_LEVEL_WARNING,
        }

    reasons.append("Primer results are present, current, Recommended, and have no recorded warnings.")
    return {
        "readiness_status": READINESS_AVAILABLE_FOR_REVIEW,
        "readiness_reasons": reasons,
        "warning_level": WARNING_LEVEL_NONE,
    }


def build_assembly_plan_summary(ds) -> Dict[str, Any]:
    """Return normalized Step 4 assembly-plan summary data from DesignSession."""
    plan = _stored_step4_plan_summary(ds)
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    primers = ds.primers if isinstance(ds.primers, list) else []
    selected_result = _selected_structured_result(plan)

    final_sequence = str(frame.get("final_sequence") or ds.optimized_seq or ds.original_seq or "")
    insert_sequence = str(ds.optimized_seq or ds.original_seq or "")
    product_size = selected_result.get("product_size") or selected_result.get("template_length")
    final_length = frame.get("total_length") or len(final_sequence) or product_size

    forward_count = 0
    reverse_count = 0
    warning_count = 0
    grade_counts = {"Recommended": 0, "Usable with Risk": 0, "Not Recommended": 0}
    for primer in primers:
        if not isinstance(primer, dict):
            continue
        if primer.get("Forward Primer (5'->3')") or primer.get("role") == "forward":
            forward_count += 1
        if primer.get("Reverse Primer (5'->3')") or primer.get("role") == "reverse":
            reverse_count += 1
        warnings = primer.get("Warnings") or primer.get("pair_warnings") or []
        warning_count += len(warnings) if isinstance(warnings, list) else 0
        grade = primer.get("Quality Grade") or primer.get("quality_grade")
        if grade in grade_counts:
            grade_counts[grade] += 1

    selected_pair_warnings = selected_result.get("pair_warnings") or []
    if selected_pair_warnings and warning_count == 0:
        warning_count = len(selected_pair_warnings)

    quality_parts = [
        f"{count} {label}"
        for label, count in grade_counts.items()
        if count
    ]
    selected_quality = selected_result.get("quality_grade")
    selected_score = selected_result.get("quality_score")
    if selected_quality:
        display_quality = "Pass-range" if selected_quality == "Recommended" else selected_quality
        score_text = f" (review value {selected_score})" if selected_score is not None else ""
        quality_parts.append(f"Active review option: {display_quality}{score_text}")
    quality_summary = "; ".join(quality_parts) or str(plan.get("best_plan_summary") or "Not available")

    primers_are_stale = getattr(ds, "primers_are_stale", None)
    is_stale = bool(primers_are_stale()) if callable(primers_are_stale) else False
    context_signature = str(getattr(ds, "primer_context_signature", "") or "")
    if is_stale:
        signature_status = "Stale"
    elif context_signature:
        signature_status = "Current"
    else:
        signature_status = "Not recorded"

    vector_metadata = _build_vector_backbone_metadata(frame, plan, selected_result)

    selected_overlap = plan.get("selected_overlap_len")
    primer_count = forward_count + reverse_count
    readiness = _build_readiness(primer_count, warning_count, is_stale, grade_counts)
    return {
        "assembly_method": ds.cloning_method or plan.get("method") or "Gibson Assembly",
        "insert_length": len(insert_sequence) if insert_sequence else None,
        "expected_product_size": product_size or final_length,
        "final_construct_length": final_length,
        "host": ds.host or "",
        **vector_metadata,
        "primer_count": primer_count,
        "forward_primer_count": forward_count,
        "reverse_primer_count": reverse_count,
        "warning_count": warning_count,
        "quality_summary": quality_summary,
        "best_plan_summary": plan.get("best_plan_summary"),
        "selected_overlap": selected_overlap,
        "selected_target_tm": plan.get("selected_target_tm"),
        "tried_combinations": plan.get("tried_combinations"),
        "stale_status": "Stale" if is_stale else "Current",
        "context_signature": context_signature,
        "selected_overlap_len": selected_overlap,
        "context_signature_status": signature_status,
        **readiness,
    }
