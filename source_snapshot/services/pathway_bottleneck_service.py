from __future__ import annotations

import json
from typing import Any

LOW_PRODUCT_THRESHOLD = 0.25
HIGH_INTERMEDIATE_THRESHOLD = 0.7
ALLOWED_PRIORITIES = {"high_review", "medium_review", "low_review", "info"}
ALLOWED_SCOPES = {"project-level", "step-level"}
SEVERE_GROWTH = {"no growth", "inhibited", "severe burden"}
MODERATE_GROWTH = {"poor", "slow", "stressed"}
FORBIDDEN = (
    "This is the bottleneck", "Bottleneck identified", "Yield will improve",
    "Predicted production", "Predicted yield", "Automatically optimized pathway",
    "Ready for Experimental Use", "Experimental Ready", "Recommended optimization",
)


def analyze_pathway_bottlenecks(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    ctx = context if isinstance(context, dict) else {}
    steps = _dict_list(_pick(ctx, "pathway_steps", "steps"))
    links = _group(_dict_list(_pick(ctx, "expression_design_links", "linked_expression_designs")), "step_id")
    comp = _group(_dict_list(_dict(_pick(ctx, "pathway_completeness", "pathway_completeness_result", "completeness_result")).get("step_summaries")), "step_id")
    project_records = _project_records(ctx)
    step_records = _step_records(ctx)
    total = len(project_records) + sum(len(v) for v in step_records.values())
    signals: list[dict[str, Any]] = []
    if total == 0:
        signals.append(_mk("missing_test_records", "info", "project-level", None, {"record_count": 0}, "Review priority: No recorded project-level or step-associated test data is available.", "Suggested next check: Add documentation records when available before using review signals for the next design iteration.", "Documentation-only recommendation. Missing records do not change pathway completeness score."))
    for step in steps:
        sid = _sid(step)
        label = _text(step.get("step_name") or step.get("name")) or f"Step {sid or 'unknown'}"
        linked = links.get(sid, [])
        records = step_records.get(sid, [])
        if not linked:
            signals.append(_mk("missing_expression_design", "medium_review", "step-level", sid, {"step_id": sid, "step_name": label, "link_status": "missing"}, f"Potential bottleneck signal: Step {label} has no recorded expression design link.", "Suggested next check: Review whether this step needs a linked expression design before the next design iteration.", "Documentation-only recommendation. This does not confirm a bottleneck or certify experimental use."))
        else:
            risk = _link_risk(sid, label, linked)
            if risk:
                signals.append(risk)
        doc = _doc_risk(sid, label, step, comp.get(sid, [{}])[0])
        if doc:
            signals.append(doc)
        if total > 0 and not records:
            signals.append(_mk("missing_test_records", "info", "step-level", sid, {"step_id": sid, "step_name": label, "record_count": 0}, f"Review priority: No recorded test data is available for step {label}.", "Suggested next check: Add documentation records for this step when available before the next design iteration.", "Documentation-only recommendation. Missing records do not change pathway completeness score."))
        for record in records:
            signals += _record_risks(record, "step-level", sid, label)
    for record in project_records:
        signals += _record_risks(record, "project-level", None, None)
    return signals


def _link_risk(step_id: int, label: str, links: list[dict[str, Any]]) -> dict[str, Any] | None:
    warnings = blocking = 0
    high = False
    evidence: dict[str, Any] = {"step_id": step_id, "step_name": label}
    for link in links:
        summary = _summary(link)
        warnings += len(_list(summary.get("warnings")))
        blocking += len(_list(summary.get("blocking_issues")))
        high = high or _high_primer(summary)
        evidence["design_id"] = evidence.get("design_id") or link.get("design_id")
        evidence["design_name"] = evidence.get("design_name") or _text(link.get("design_name"))
        evidence["primer_risk"] = evidence.get("primer_risk") or _primer(summary)
    if warnings == 0 and blocking == 0 and not high:
        return None
    evidence.update({"warning_count": warnings, "blocking_issue_count": blocking})
    priority = "high_review" if blocking or high else "medium_review"
    return _mk("linked_design_validation_risk", priority, "step-level", step_id, evidence, f"Potential bottleneck signal: Recorded validation notes for step {label} suggest this linked design should be reviewed before the next design iteration.", "Suggested next check: Review validation warnings, blocking issues, and primer risk notes for the linked expression design.", "Documentation-only recommendation. This does not change primer risk status or certify experimental use.")


def _doc_risk(step_id: int, label: str, step: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any] | None:
    missing = [_text(v) for v in _list(summary.get("missing_fields")) + _list(summary.get("missing_items")) if _text(v)]
    seq_missing = not _text(step.get("gene_sequence") or step.get("sequence"))
    if seq_missing:
        missing.append("sequence")
    missing = _dedupe(missing)
    if not missing:
        return None
    priority = "medium_review" if seq_missing else "low_review"
    msg = f"Potential bottleneck signal: Step {label} is missing sequence documentation and should be reviewed before the next design iteration." if seq_missing else f"Recorded pattern suggests review priority for step {label}: existing completeness evidence lists missing documentation fields."
    return _mk("incomplete_step_documentation", priority, "step-level", step_id, {"step_id": step_id, "step_name": label, "missing_fields": missing, "sequence_present": not seq_missing}, msg, "Suggested next check: Review missing sequence or step documentation fields.", "Documentation-only recommendation. This does not change pathway completeness score.")


def _record_risks(record: dict[str, Any], scope: str, step_id: int | None, label: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    related = step_id if step_id is not None else _int(record.get("step_id"))
    product = _num(record, "yield_value", "product_value", "titer", "product_titer", "productivity")
    intermediate = _num(record, "intermediate_accumulation")
    if product is not None and intermediate is not None and product <= LOW_PRODUCT_THRESHOLD and intermediate >= HIGH_INTERMEDIATE_THRESHOLD:
        out.append(_mk("product_low_intermediate_high", "high_review", scope, related, {"record_id": record.get("record_id") or record.get("id"), "step_id": related, "condition": _text(record.get("condition")), "product_value": product, "intermediate_accumulation": intermediate}, f"Recorded pattern suggests review priority for {label or 'this record'}: low final product appears alongside high intermediate accumulation.", "Suggested next check: Review the associated step, condition notes, and linked validation summaries for the next design iteration.", "Documentation-only recommendation. This is not a production prediction and does not confirm a bottleneck."))
    growth = (_text(record.get("growth_status")) or "").lower()
    priority = "high_review" if growth in SEVERE_GROWTH else "medium_review" if growth in MODERATE_GROWTH else None
    if priority:
        out.append(_mk("poor_growth_recorded", priority, scope, related, {"record_id": record.get("record_id") or record.get("id"), "step_id": related, "condition": _text(record.get("condition")), "growth_status": growth}, "Potential bottleneck signal: Recorded growth status suggests this condition should be reviewed before the next design iteration.", "Suggested next check: Review host condition notes and linked validation summaries for the recorded growth status.", "Documentation-only recommendation. This does not confirm a bottleneck or provide optimization instructions."))
    return out


def _mk(signal_type: str, priority: str, scope: str, related_step_id: int | None, evidence: dict[str, Any], message: str, suggested_next_check: str, boundary_note: str) -> dict[str, Any]:
    if priority not in ALLOWED_PRIORITIES or scope not in ALLOWED_SCOPES:
        raise ValueError("Invalid priority or scope.")
    signal = {"signal_type": signal_type, "priority": priority, "scope": scope, "related_step_id": related_step_id, "evidence": evidence, "message": message, "suggested_next_check": suggested_next_check, "boundary_note": boundary_note}
    _safe(signal)
    return signal


def _safe(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _safe(item)
    elif isinstance(value, list):
        for item in value:
            _safe(item)
    elif isinstance(value, str):
        low = value.lower()
        for phrase in FORBIDDEN:
            if phrase.lower() in low:
                raise ValueError(f"Forbidden wording detected: {phrase}")


def _summary(link: dict[str, Any]) -> dict[str, Any]:
    raw = link.get("validation_summary_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _high_primer(summary: dict[str, Any]) -> bool:
    label = (_primer(summary) or "").lower()
    return summary.get("not_recommended_for_experimental_use") is True or summary.get("high_risk_primer") is True or "not recommended" in label or "high risk" in label or "high-risk" in label


def _primer(summary: dict[str, Any]) -> str | None:
    for key in ("primer_risk", "primer_status", "status", "summary"):
        text = _text(summary.get(key))
        if text:
            return text
    return None


def _pick(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return [value] if isinstance(value, dict) else []


def _group(items: list[dict[str, Any]], key: str) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        sid = _int(item.get(key))
        if sid is not None:
            grouped.setdefault(sid, []).append(item)
    return grouped


def _project_records(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    records = _dict_list(_pick(ctx, "project_test_records", "pathway_test_records", "test_records"))
    return [record for record in records if record.get("step_id") is None and str(record.get("scope") or "project").lower() != "step"]


def _step_records(ctx: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    raw = _pick(ctx, "step_test_records", "pathway_step_test_records")
    grouped: dict[int, list[dict[str, Any]]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            sid = _int(key)
            if sid is not None:
                grouped[sid] = _dict_list(value)
    else:
        for record in _dict_list(raw):
            sid = _int(record.get("step_id"))
            if sid is not None:
                grouped.setdefault(sid, []).append(record)
    return grouped


def _sid(step: dict[str, Any]) -> int:
    return _int(step.get("id")) or _int(step.get("step_id")) or 0


def _num(record: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(record.get(key))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out

