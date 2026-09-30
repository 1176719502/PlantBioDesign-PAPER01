from __future__ import annotations

from typing import Any

import json

import streamlit as st


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _gap_priority_label(priority: str) -> str:
    return {
        "high_review": "Documentation review prompt",
        "medium_review": "Documentation gap",
    }.get(priority, "Documentation review prompt")


def _humanize_signal_type(signal_type: str) -> str:
    text = str(signal_type or "").strip().replace("_", " ").replace("-", " ")
    return " ".join(part for part in text.split() if part).title() or "Review Signal"


def _pathway_step_display_lookup(steps: list[dict[str, Any]] | None) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for display_index, step in enumerate(steps or [], start=1):
        if not isinstance(step, dict):
            continue
        try:
            step_id = int(step.get("id"))
        except (TypeError, ValueError):
            continue
        title = str(step.get("step_name") or step.get("name") or "").strip()
        lookup[step_id] = {"display_index": display_index, "title": title}
    return lookup


def _pathway_step_display_label(signal: dict[str, Any], step_lookup: dict[int, dict[str, Any]] | None = None) -> str:
    related_step_id = signal.get("related_step_id")
    if related_step_id is None:
        return "Project-level"
    try:
        step_id = int(related_step_id)
    except (TypeError, ValueError):
        return "Pathway Step"
    step_info = (step_lookup or {}).get(step_id)
    if step_info:
        label = f"Pathway Step {step_info['display_index']}"
        if step_info.get("title"):
            label = f"{label} - {step_info['title']}"
        return label
    step_order = _safe_int(signal.get("step_order"), 0)
    if step_order:
        return f"Pathway Step {step_order}"
    return "Pathway Step"


def _review_signal_detail(signal: dict[str, Any]) -> str:
    signal_type = str(signal.get("signal_type") or "").strip()
    title_map = {
        "missing_expression_design": "Missing linked expression design",
        "incomplete_step_documentation": "Missing sequence documentation",
        "missing_test_records": "No step-associated test record",
    }
    return title_map.get(signal_type, _humanize_signal_type(signal_type))


def _review_signal_title(signal: dict[str, Any], step_lookup: dict[int, dict[str, Any]] | None = None) -> str:
    return f"{_pathway_step_display_label(signal, step_lookup)}: {_review_signal_detail(signal)}"


def _render_signal_evidence(signal: dict[str, Any], *, include_no_missing_documentation_line: bool) -> None:
    evidence = signal.get("evidence")
    if not evidence:
        return
    if isinstance(evidence, dict):
        text: list[str] = []
        if evidence.get("sequence_present") is False or evidence.get("sequence_doc_status") in {"missing", "not recorded", "absent"}:
            text.append("Sequence documentation is not recorded for this step.")
        if evidence.get("linked_design_present") is False or evidence.get("link_status") in {"missing", "not linked", "unlinked"}:
            text.append("No linked Expression Wizard design is recorded for this step.")
        if evidence.get("test_record_count") == 0 or evidence.get("test_record_status") in {"missing", "not recorded", "absent"}:
            text.append("No step-associated test record is recorded for this step.")
        if include_no_missing_documentation_line and evidence.get("missing_documentation") is False:
            text = ["No missing documentation recorded."]
        evidence_text = " ".join(text) if text else str(evidence)
    else:
        evidence_text = str(evidence)
    st.caption(f"Evidence summary: {evidence_text}")


def _count_primer_risk_links(expression_links: list[dict[str, Any]]) -> int:
    count = 0
    for link in expression_links:
        raw = link.get("validation_summary_json")
        summary: dict[str, Any] = {}
        if isinstance(raw, dict):
            summary = raw
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    summary = parsed
            except (TypeError, json.JSONDecodeError):
                pass
        primer_label = ""
        for key in ("primer_risk", "primer_status", "status"):
            text = str(summary.get(key) or "").strip().lower()
            if text:
                primer_label = text
                break
        has_risk = (
            summary.get("not_recommended_for_experimental_use") is True
            or summary.get("high_risk_primer") is True
            or "not recommended" in primer_label
            or "high risk" in primer_label
            or "high-risk" in primer_label
        )
        if has_risk:
            count += 1
    return count


def _step_test_counts(test_records: list[dict[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for record in test_records:
        try:
            step_id = int(record.get("step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        counts[step_id] = counts.get(step_id, 0) + 1
    return counts


def render_review_signals_tab(signals: list[dict[str, Any]], steps: list[dict[str, Any]] | None = None) -> None:
    st.subheader("Documentation-only review signals")
    st.caption(
        "Review Signals are documentation-only prompts for unresolved questions, source review, documentation gaps, "
        "manual follow-up notes, record consistency checks, and evidence-chain review."
    )
    st.caption(
        "They are not experimental judgments, predictions, optimization instructions, readiness approval, "
        "recommendation engine output, experimental guidance, action instructions, or protocol generation."
    )
    st.caption(
        "Review Signals do not identify established results or forecast production. They are transient prompts for reviewing the current workspace documentation context."
    )
    if not signals:
        st.info("No documentation-only review signals were generated from the currently recorded data.")
        return
    step_lookup = _pathway_step_display_lookup(steps)
    for signal in signals:
        priority = str(signal.get("priority") or "").strip()
        related_step_label = _pathway_step_display_label(signal, step_lookup)
        title = _review_signal_title(signal, step_lookup)
        step_name = str(signal.get("step_name") or signal.get("step") or "").strip()
        message = str(signal.get("message") or "").strip()
        with st.container(border=True):
            c1, c2 = st.columns([3, 1], gap="small")
            with c1:
                st.markdown(f"**{title}**")
                if step_name:
                    st.caption(step_name)
                if priority:
                    st.caption(f"Priority: {priority}")
                if message:
                    st.caption(message)
                suggested_next_check = str(signal.get("suggested_next_check") or "").strip()
                if suggested_next_check:
                    st.caption(f"Suggested next check: {suggested_next_check}")
            with c2:
                st.caption(related_step_label)
            _render_signal_evidence(signal, include_no_missing_documentation_line=True)
            if signal.get("boundary_note"):
                st.caption(f"Boundary note: {signal.get('boundary_note')}")


def render_review_signals_summary(
    *,
    review_signal_summary: dict[str, Any],
    expression_links: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
) -> None:
    with st.container(border=True):
        st.markdown("**Review Signals Summary**")
        s1, s2, s3, s4 = st.columns(4, gap="small")
        with s1:
            st.markdown("**Total review signals**")
            st.markdown(str(review_signal_summary["total_review_signals"]))
        with s2:
            st.markdown("**High review**")
            st.markdown(str(review_signal_summary["high_review_count"]))
        with s3:
            st.markdown("**Medium review**")
            st.markdown(str(review_signal_summary["medium_review_count"]))
        with s4:
            st.markdown("**Info**")
            st.markdown(str(review_signal_summary["info_count"]))

    with st.container(border=True):
        st.markdown("**Linked Expression Wizard Designs**")
        primer_risk_count = _count_primer_risk_links(expression_links)
        ld1, ld2 = st.columns(2, gap="small")
        with ld1:
            st.markdown("**Linked designs**")
            st.markdown(str(len(expression_links)))
        with ld2:
            st.markdown("**With primer-risk status**")
            st.markdown(str(primer_risk_count))
        if primer_risk_count > 0:
            st.caption(
                "Primer-risk status is recorded from linked Expression Wizard validation. "
                "This does not represent broader biological risk."
            )

    with st.container(border=True):
        st.markdown("**Test Records Coverage**")
        total_steps = len(steps)
        step_test_counts = _step_test_counts(test_records)
        steps_with_records = sum(1 for step in steps if int(step["id"]) in step_test_counts)
        st.markdown(f"**{steps_with_records} / {total_steps}** steps documented with test records")
        st.caption("Coverage is based on recorded step-associated test records.")


def render_documentation_gaps(review_signals: list[dict[str, Any]], steps: list[dict[str, Any]] | None = None) -> None:
    high_medium = [s for s in review_signals if s.get("priority") in ("high_review", "medium_review")]
    st.subheader("Documentation Gaps")
    st.caption("These are pathway step documentation review prompts, not application workflow steps.")
    st.caption("These are documentation review prompts only.")
    if not high_medium:
        st.success("No high-review or medium-review documentation gaps recorded.")
        return
    step_lookup = _pathway_step_display_lookup(steps)
    for signal in high_medium:
        priority = str(signal.get("priority") or "")
        title = _review_signal_title(signal, step_lookup)
        message = str(signal.get("message") or "").strip()
        step_label = _pathway_step_display_label(signal, step_lookup)
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(f"Priority: {_gap_priority_label(priority)} - {step_label}")
            if message:
                st.caption(message)
            _render_signal_evidence(signal, include_no_missing_documentation_line=False)
            if signal.get("suggested_next_check"):
                st.caption(f"Suggested next check: {signal.get('suggested_next_check')}")
            if signal.get("boundary_note"):
                st.caption(f"Boundary note: {signal.get('boundary_note')}")
