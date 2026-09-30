from __future__ import annotations

from typing import Any


STEP_SCORE_WEIGHTS = {
    "substrate": 15,
    "product": 15,
    "enzyme": 10,
    "gene": 10,
    "gene_sequence": 25,
    "expression_design": 25,
}


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _links_by_step(expression_links: list[dict[str, Any]] | None) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for link in expression_links or []:
        try:
            step_id = int(link.get("step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        grouped.setdefault(step_id, []).append(link)
    return grouped


def _normalize_step_id(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _step_associated_test_records(test_records: list[dict[str, Any]] | None) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in test_records or []:
        if not isinstance(record, dict):
            continue
        step_id = _normalize_step_id(record.get("step_id"))
        if step_id is None:
            step_id = _normalize_step_id(record.get("pathway_step_id"))
        if step_id is None:
            step_id = _normalize_step_id(record.get("related_step_id"))
        if step_id is None:
            step_id = _normalize_step_id(record.get("step_order"))
        if step_id is None:
            continue
        grouped.setdefault(step_id, []).append(record)
    return grouped


def _status_from_score(score: int, missing_count: int) -> str:
    if score >= 85 and missing_count == 0:
        return "Mostly Complete"
    if score >= 60:
        return "In Progress"
    return "Incomplete"


def _sequence_recorded(step: dict[str, Any]) -> bool:
    return _has_text(step.get("gene_sequence"))


def _build_step_summary(
    step: dict[str, Any],
    linked_designs: list[dict[str, Any]],
    step_test_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        step_id = int(step.get("id"))
    except (TypeError, ValueError):
        step_id = 0
    try:
        step_order = int(step.get("step_order") or 0)
    except (TypeError, ValueError):
        step_order = 0

    has_sequence = _sequence_recorded(step)
    has_expression_design = bool(linked_designs)
    has_step_test_record = bool(step_test_records)

    missing_items: list[str] = []
    score = 0

    if _has_text(step.get("substrate")):
        score += STEP_SCORE_WEIGHTS["substrate"]
    else:
        missing_items.append(f"Step {step_order or step_id} is missing substrate.")

    if _has_text(step.get("product")):
        score += STEP_SCORE_WEIGHTS["product"]
    else:
        missing_items.append(f"Step {step_order or step_id} is missing product.")

    if _has_text(step.get("enzyme_name")):
        score += STEP_SCORE_WEIGHTS["enzyme"]
    else:
        missing_items.append(f"Step {step_order or step_id} is missing enzyme.")

    if _has_text(step.get("gene_name")):
        score += STEP_SCORE_WEIGHTS["gene"]
    else:
        missing_items.append(f"Step {step_order or step_id} is missing gene.")

    if has_sequence:
        score += STEP_SCORE_WEIGHTS["gene_sequence"]
    else:
        missing_items.append(f"Step {step_order or step_id} is missing gene sequence.")

    if has_expression_design:
        score += STEP_SCORE_WEIGHTS["expression_design"]
    else:
        missing_items.append(f"Step {step_order or step_id} has no linked expression design.")

    if has_expression_design:
        missing_items = [
            item
            for item in missing_items
            if "linked expression design" not in item.lower()
        ]

    return {
        "step_id": step_id,
        "step_order": step_order,
        "step_name": step.get("step_name") or f"Step {step_order or step_id}",
        "score": score,
        "missing_items": missing_items,
        "has_expression_design": has_expression_design,
        "sequence_recorded": has_sequence,
        "has_test_records": has_step_test_record,
    }


def build_pathway_review_signals(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None = None,
    test_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    safe_steps = [step for step in (steps or []) if isinstance(step, dict)]
    links_lookup = _links_by_step(expression_links)
    safe_test_records = [record for record in (test_records or []) if isinstance(record, dict)]
    test_records_by_step = _step_associated_test_records(safe_test_records)

    signals: list[dict[str, Any]] = []
    for step in safe_steps:
        try:
            step_id = int(step.get("id") or 0)
        except (TypeError, ValueError):
            step_id = 0
        try:
            step_order = int(step.get("step_order") or 0)
        except (TypeError, ValueError):
            step_order = 0

        has_sequence = _sequence_recorded(step)
        has_link = bool(links_lookup.get(step_id))
        has_test_record = bool(test_records_by_step.get(step_id))

        if not has_sequence:
            signals.append(
                {
                    "signal_type": "incomplete_step_documentation",
                    "priority": "medium_review",
                    "scope": "documentation_gap",
                    "related_step_id": step_id,
                    "message": f"Step {step_order or step_id} is missing gene sequence.",
                    "documentation_key": "gene_sequence",
                    "evidence": {
                        "step_id": step_id,
                        "sequence_present": False,
                        "sequence_doc_status": "missing",
                    },
                    "suggested_next_check": "Record gene_sequence for this step.",
                    "boundary_note": "Documentation-only prompt; no biological interpretation.",
                }
            )
        if not has_link:
            signals.append(
                {
                    "signal_type": "missing_expression_design",
                    "priority": "medium_review",
                    "scope": "documentation_gap",
                    "related_step_id": step_id,
                    "message": f"Step {step_order or step_id} has no linked Expression Wizard design.",
                    "documentation_key": "expression_design",
                    "evidence": {
                        "step_id": step_id,
                        "linked_design_present": False,
                        "link_status": "missing",
                    },
                    "suggested_next_check": "Link an Expression Wizard design if one exists.",
                    "boundary_note": "Documentation-only prompt; no biological interpretation.",
                }
            )
        if not has_test_record:
            signals.append(
                {
                    "signal_type": "missing_test_records",
                    "priority": "info",
                    "scope": "documentation_prompt",
                    "related_step_id": step_id,
                    "message": f"Step {step_order or step_id} has no step-associated test record.",
                    "documentation_key": "test_records",
                    "evidence": {
                        "step_id": step_id,
                        "test_record_count": 0,
                        "test_record_status": "missing",
                    },
                    "suggested_next_check": "Add a step-associated test record if available.",
                    "boundary_note": "Documentation-only prompt; no biological interpretation.",
                }
            )
    return signals


def filter_documentation_gap_signals(signals: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        signal
        for signal in (signals or [])
        if signal.get("signal_type") in {"missing_expression_design", "incomplete_step_documentation"}
    ]


def summarize_review_signals(signals: list[dict[str, Any]] | None) -> dict[str, int]:
    safe_signals = [signal for signal in (signals or []) if isinstance(signal, dict)]
    return {
        "total_review_signals": len(safe_signals),
        "high_review_count": sum(1 for signal in safe_signals if signal.get("priority") == "high_review"),
        "medium_review_count": sum(1 for signal in safe_signals if signal.get("priority") == "medium_review"),
        "info_count": sum(1 for signal in safe_signals if signal.get("priority") == "info"),
        "documentation_gap_count": len(filter_documentation_gap_signals(safe_signals)),
        "missing_test_record_prompt_count": sum(1 for signal in safe_signals if signal.get("signal_type") == "missing_test_records"),
    }


def build_dbt_step_evidence_matrix_rows(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None = None,
    test_records: list[dict[str, Any]] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    safe_steps = [step for step in (steps or []) if isinstance(step, dict)]
    links_lookup = _links_by_step(expression_links)
    safe_test_records = [record for record in (test_records or []) if isinstance(record, dict)]
    test_records_by_step = _step_associated_test_records(safe_test_records)
    signals_by_step: dict[int, list[dict[str, Any]]] = {}
    for signal in (review_signals or []):
        if not isinstance(signal, dict):
            continue
        try:
            step_id = int(signal.get("related_step_id") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        signals_by_step.setdefault(step_id, []).append(signal)

    rows: list[dict[str, Any]] = []
    for step in safe_steps:
        try:
            step_id = int(step.get("id") or 0)
        except (TypeError, ValueError):
            step_id = 0
        step_signals = signals_by_step.get(step_id, [])
        has_sequence = _sequence_recorded(step)
        has_link = bool(links_lookup.get(step_id))
        has_test_record = bool(test_records_by_step.get(step_id))
        missing_summary = "No missing documentation recorded"
        if not has_link and not has_sequence and not has_test_record:
            missing_summary = "Missing sequence; no linked expression design; no step-associated test record"
        elif not has_link and not has_sequence:
            missing_summary = "Missing sequence; no linked expression design"
        elif not has_link and not has_test_record:
            missing_summary = "No linked expression design; no step-associated test record"
        elif not has_sequence and not has_test_record:
            missing_summary = "Missing sequence; no step-associated test record"
        elif not has_link:
            missing_summary = "No linked expression design"
        elif not has_sequence:
            missing_summary = "Missing sequence"
        elif not has_test_record:
            missing_summary = "No step-associated test record"
        rows.append(
            {
                "step_order": step.get("step_order"),
                "step_name": step.get("step_name") or f"Step {step.get('step_order') or step_id}",
                "reaction": step.get("reaction_name") or step.get("reaction") or step.get("substrate") or "",
                "gene_or_enzyme": step.get("gene_name") or step.get("enzyme_name") or "",
                "sequence_recorded": has_sequence,
                "expression_design_linked": has_link,
                "test_record_exists": has_test_record,
                "review_signal_count": len(step_signals),
                "missing_documentation_summary": missing_summary,
            }
        )
    return rows


def build_pathway_completeness(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a minimal documentation-oriented pathway completeness summary."""
    safe_project = project if isinstance(project, dict) else {}
    safe_steps = [step for step in (steps or []) if isinstance(step, dict)]
    links_lookup = _links_by_step(expression_links)

    project_missing: list[str] = []
    if not _has_text(safe_project.get("target_product")):
        project_missing.append("Pathway project is missing target product.")
    if not safe_steps:
        project_missing.append("Pathway project has no pathway steps.")

    step_test_records = _step_associated_test_records(safe_test_records)
    step_summaries = []
    for step in safe_steps:
        try:
            step_id = int(step.get("id") or 0)
        except (TypeError, ValueError):
            step_id = 0
        step_summaries.append(
            _build_step_summary(step, links_lookup.get(step_id, []), step_test_records.get(step_id, []))
        )
    step_missing = [
        item
        for summary in step_summaries
        for item in summary["missing_items"]
    ]
    missing_items = project_missing + step_missing

    if not safe_steps:
        score = 0
    else:
        score = round(sum(summary["score"] for summary in step_summaries) / len(step_summaries))
        if project_missing:
            score = min(score, 80)

    return {
        "score": int(score),
        "status": _status_from_score(int(score), len(missing_items)),
        "missing_items": missing_items,
        "step_summaries": step_summaries,
        "project_missing_items": project_missing,
    }


def build_pathway_completeness(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a minimal documentation-oriented pathway completeness summary."""
    safe_project = project if isinstance(project, dict) else {}
    safe_steps = [step for step in (steps or []) if isinstance(step, dict)]
    links_lookup = _links_by_step(expression_links)

    project_missing: list[str] = []
    if not _has_text(safe_project.get("target_product")):
        project_missing.append("Pathway project is missing target product.")
    if not safe_steps:
        project_missing.append("Pathway project has no pathway steps.")

    step_summaries = [
        _build_step_summary(step, links_lookup.get(int(step.get("id") or 0), []))
        for step in safe_steps
    ]
    step_missing = [
        item
        for summary in step_summaries
        for item in summary["missing_items"]
    ]
    missing_items = project_missing + step_missing

    if not safe_steps:
        score = 0
    else:
        score = round(sum(summary["score"] for summary in step_summaries) / len(step_summaries))
        if project_missing:
            score = min(score, 80)

    return {
        "score": int(score),
        "status": _status_from_score(int(score), len(missing_items)),
        "missing_items": missing_items,
        "step_summaries": step_summaries,
        "project_missing_items": project_missing,
    }
