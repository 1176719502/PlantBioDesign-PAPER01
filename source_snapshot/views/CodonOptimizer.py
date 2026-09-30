# -*- coding: utf-8 -*-
"""
views/CodonOptimizer.py  --  Codon Usage Preview standalone module (Beta).

Thin UI wrapper. Standalone Codon Usage Preview UI delegates computational
logic to core.codon_optimizer. This file should remain presentation-only
during v0.1 cleanup and contain only UI and event wiring.

Public API
----------
render(change_page=None) -> None
"""
from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

CODON_USAGE_VISIBLE_HELPER_COPY = (
    "Codon Usage Preview is a documentation-only preview/status helper. "
    "It is not automatic codon optimization, expression or yield optimization, prediction, "
    "wet-lab protocol guidance, or a replacement for expert/company review."
)

CODON_USAGE_PREVIEW_CONTEXT_COPY = (
    "Codon Usage Preview is a candidate sequence documentation review helper and local computational preview "
    "for documentation-only review context. "
    "It is not an expression/yield optimization engine, not expression optimization, not prediction, "
    "not recommendation, not validation, not readiness approval, and not a wet-lab protocol. "
    "It does not predict expression, does not predict yield, does not optimize yield, "
    "does not optimize pathways, does not certify experimental readiness, and does not provide wet-lab protocols."
)

CODON_USAGE_HANDOFF_COPY = (
    "Send this codon usage preview as a transient Step 3 candidate for Expression Wizard documentation review. "
    "This handoff does not modify Step 1 input, does not complete Step 3, does not advance the workflow, "
    "and is not prediction, not recommendation, not validation, not readiness approval, and not a wet-lab protocol."
)

CODON_USAGE_EMPTY_STATE_COPY = (
    "Enter a DNA coding sequence of at least 30 bp, choose the host table, then generate a local codon usage preview. "
    "Results will appear as review-context metrics, diagnostic tables, a candidate sequence preview, and documentation notes."
)

CODON_USAGE_STATUS_RECORD_COPY = (
    "Current software status: codon usage preview and codon status documentation only. "
    "BioDesign Studio records the original CDS source, host context, preview provider, and manual/company review cue. "
    "It does not automatically optimize expression, choose a best sequence, predict yield, guarantee expression, "
    "or replace expert/company review."
)

CODON_USAGE_STATUS_READBACK_HELPER_COPY = (
    "Status readback records the CDS source, host context, preview provider, documentation-check status, and manual/company review cue."
)

CODON_USAGE_RESULT_HELPER_COPY = (
    "Preview generated for documentation review. Review the preview/readback output and diagnostics before using it as design support."
)

CODON_USAGE_ERROR_CONTEXT_COPY = (
    "The preview was not generated. Review the input requirements and existing check messages, then try again. "
    "No Wizard state, saved design snapshot, or project documentation record was changed."
)

CODON_DRAFT_METRICS_HELPER_COPY = (
    "Codon draft metrics are review metrics only for codon usage review. "
    "This preview-only readback is not a sequence rewrite, not an expression prediction, "
    "and manual review required remains visible."
)

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clean(seq: str) -> str:
    """Strip FASTA headers, whitespace; upper-case."""
    lines = [ln for ln in seq.strip().splitlines() if not ln.startswith(">")]
    return "".join(lines).replace(" ", "").upper()


def _gc(seq: str) -> float:
    s = seq.upper()
    return round((s.count("G") + s.count("C")) / len(s) * 100, 1) if s else 0.0


def _build_hit_dataframe(hits: list[dict], columns: list[tuple[str, str]]) -> pd.DataFrame:
    """Return a compact diagnostics table for Streamlit display."""
    rows = []
    for hit in hits or []:
        rows.append({label: hit.get(key) for key, label in columns})
    return pd.DataFrame(rows)


def _build_rare_codon_summary(rare_codons: list[dict]) -> tuple[int, int, float]:
    """Summarize rare codon diagnostics for compact metrics."""
    total_hits = sum(int(item.get("count", 0) or 0) for item in rare_codons or [])
    unique_hits = len(rare_codons or [])
    total_pct = round(sum(float(item.get("percentage", 0.0) or 0.0) for item in rare_codons or []), 2)
    return total_hits, unique_hits, total_pct


def _format_delta(after_value: float | int | None, before_value: float | int | None, precision: int = 4) -> str:
    """Format a signed numeric delta for report export."""
    if after_value is None or before_value is None:
        return "n/a"
    return f"{after_value - before_value:+.{precision}f}"


def _build_optimization_report(
    host: str,
    table_metadata: dict,
    input_sequence: str,
    optimized_sequence: str,
    cai_before: float,
    cai_after: float,
    gc_before: float | None,
    gc_after: float | None,
    codon_changes: int,
    protein_preserved: bool,
    rare_before: int,
    rare_after: int,
    forbidden_before: int,
    forbidden_after: int,
    repeat_before: int,
    repeat_after: int,
    gc_outlier_before: int,
    gc_outlier_after: int,
    unresolved_warnings: list[str],
) -> str:
    """Build a compact plain-text report from the current codon usage preview."""
    warnings_text = "None" if not unresolved_warnings else "\n".join(
        f"- {warning}" for warning in unresolved_warnings
    )
    gc_before_text = f"{gc_before:.1f}%" if gc_before is not None else "n/a"
    gc_after_text = f"{gc_after:.1f}%" if gc_after is not None else "n/a"
    gc_delta_text = (
        f"{gc_after - gc_before:+.1f}%"
        if gc_before is not None and gc_after is not None
        else "n/a"
    )
    metadata = table_metadata if isinstance(table_metadata, dict) else {}

    return "\n".join(
        [
            "Codon Usage Preview Report",
            "==========================",
            f"Host: {host}",
            f"Scope: {CODON_USAGE_PREVIEW_CONTEXT_COPY}",
            f"Status record: {CODON_USAGE_STATUS_RECORD_COPY}",
            "",
            "Sequence Summary",
            "----------------",
            f"Input length: {len(input_sequence)} bp",
            f"Preview length: {len(optimized_sequence)} bp",
            f"Codon changes: {codon_changes}",
            f"Protein preserved: {'Yes' if protein_preserved else 'No'}",
            "",
            "CAI",
            "---",
            f"Input: {cai_before:.4f}" if cai_before else "Input: n/a",
            f"Preview: {cai_after:.4f}" if cai_after else "Preview: n/a",
            f"Delta: {_format_delta(cai_after, cai_before, 4)}",
            "",
            "GC Content",
            "----------",
            f"Input: {gc_before_text}",
            f"Preview: {gc_after_text}",
            f"Delta: {gc_delta_text}",
            "",
            "Constraint Summary",
            "------------------",
            f"Rare codons in input: {rare_before}",
            f"Rare codons in preview: {rare_after}",
            f"Forbidden sites in input: {forbidden_before}",
            f"Forbidden sites in preview: {forbidden_after}",
            f"Repeat issues in input: {repeat_before}",
            f"Repeat issues in preview: {repeat_after}",
            f"Local GC outliers in input: {gc_outlier_before}",
            f"Local GC outliers in preview: {gc_outlier_after}",
            "",
            "Unresolved Warnings",
            "-------------------",
            warnings_text,
            "",
            "Codon Status Readback",
            "---------------------",
            "Original CDS source: user-provided or Wizard-loaded CDS",
            "Codon optimized?: not claimed by BioDesign Studio",
            "Preview sequence provider: local Codon Usage Preview",
            f"Target expression system / host context for review: {host}",
            f"Selected codon usage table: {metadata.get('host_label') or host}",
            f"Table ID: {metadata.get('table_id') or 'not recorded'}",
            f"Organism or scope: {metadata.get('organism_or_scope') or 'not recorded'}",
            f"Source/provenance note: {metadata.get('source_note') or 'not recorded'}",
            f"Version/date note: {metadata.get('version_or_date_note') or 'not recorded'}",
            f"Provenance status: {metadata.get('provenance_status') or 'not recorded'}",
            f"Future rewrite draft status: {metadata.get('draft_use_status') or 'not recorded'}",
            f"Limitation note: {metadata.get('limitation_note') or 'not recorded'}",
            f"Documentation review note: {metadata.get('documentation_review_note') or 'not recorded'}",
            f"Manual review required: {'Yes' if metadata.get('manual_review_required') else 'Not recorded'}",
            "Sequence verification status: documentation checks only; not experimental validation",
            "Manual/company review cue: required before downstream biological decisions",
            "",
            "Candidate Sequence Preview",
            "--------------------------",
            optimized_sequence or "n/a",
            "",
        ]
    )


def _build_rare_codon_lookup(rare_codons: list[dict]) -> dict[str, dict]:
    """Map rare-codon diagnostics by codon for quick lookup."""
    return {
        str(item.get("codon", "")).upper(): item
        for item in rare_codons or []
        if item.get("codon")
    }


def _build_change_impact_summary(
    history: list[dict],
    before_diag: dict,
    after_diag: dict,
    host: str,
) -> dict:
    """Summarize substitution history into compact impact categories."""
    if not history:
        return {
            "summary": {
                "cai_primary": 0,
                "constraint_driven": 0,
                "rare_codon_relief": 0,
                "total": 0,
            },
            "by_amino_acid": [],
            "by_frequency_effect": [],
            "rows": [],
        }

    try:
        from Bio.Seq import Seq
        from core.codon_optimizer import CODON_TABLES
    except Exception:
        return {
            "summary": {
                "cai_primary": 0,
                "constraint_driven": 0,
                "rare_codon_relief": 0,
                "total": len(history),
            },
            "by_amino_acid": [],
            "by_frequency_effect": [],
            "rows": [],
        }

    codon_table = CODON_TABLES.get(host) or CODON_TABLES.get("E.coli", {})
    before_rare_lookup = _build_rare_codon_lookup(before_diag.get("rare_codons") or [])
    after_rare_lookup = _build_rare_codon_lookup(after_diag.get("rare_codons") or [])

    summary_counts = Counter()
    aa_counts = Counter()
    effect_counts = Counter()
    impact_rows = []

    for entry in history:
        from_codon = str(entry.get("from_codon", "")).upper()
        to_codon = str(entry.get("to_codon", "")).upper()
        if not from_codon or not to_codon:
            continue

        aa = str(Seq(from_codon).translate()) if len(from_codon) == 3 else "?"
        if aa == "*":
            aa = "Stop"

        from_freq = float(codon_table.get(from_codon, 0.0) or 0.0)
        to_freq = float(codon_table.get(to_codon, 0.0) or 0.0)
        freq_delta = round(to_freq - from_freq, 2)
        score_delta = round(float(entry.get("score_before", 0.0) or 0.0) - float(entry.get("score_after", 0.0) or 0.0), 6)

        from_rare = from_codon in before_rare_lookup
        to_rare = to_codon in after_rare_lookup
        rare_relieved = from_rare and not to_rare

        if freq_delta > 0:
            effect_label = "Higher host-frequency codon"
        elif freq_delta < 0:
            effect_label = "Lower host-frequency codon"
        else:
            effect_label = "Similar host-frequency codon"

        if entry.get("pass") == "cai_sweep":
            primary_label = "CAI-driven"
            summary_counts["cai_primary"] += 1
        else:
            primary_label = "Constraint-driven"
            summary_counts["constraint_driven"] += 1

        if rare_relieved:
            summary_counts["rare_codon_relief"] += 1

        aa_counts[aa] += 1
        effect_counts[effect_label] += 1
        impact_rows.append(
            {
                "Review Stage": entry.get("pass"),
                "Codon Index": entry.get("codon_index"),
                "AA": aa,
                "From": from_codon,
                "To": to_codon,
                "Host Frequency Δ": freq_delta,
                "Score Improvement": score_delta,
                "Primary Driver": primary_label,
                "Rare Codon Relief": "Yes" if rare_relieved else "No",
                "Frequency Effect": effect_label,
            }
        )

    amino_rows = [
        {"Amino Acid": aa, "Edits": count}
        for aa, count in sorted(aa_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    effect_rows = [
        {"Effect": label, "Edits": count}
        for label, count in sorted(effect_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "summary": {
            "cai_primary": summary_counts["cai_primary"],
            "constraint_driven": summary_counts["constraint_driven"],
            "rare_codon_relief": summary_counts["rare_codon_relief"],
            "total": len(impact_rows),
        },
        "by_amino_acid": amino_rows,
        "by_frequency_effect": effect_rows,
        "rows": impact_rows,
    }


def _show_hit_table(title: str, hits: list[dict], columns: list[tuple[str, str]], empty_message: str) -> None:
    """Render an optional diagnostics table with a stable empty state."""
    with st.expander(title, expanded=False):
        if hits:
            st.dataframe(
                _build_hit_dataframe(hits, columns),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(empty_message)


def _render_compact_review_rows(rows: list[tuple[str, str]], first_column: str = "Review item") -> None:
    """Render compact status/readback rows without large metric typography."""
    st.dataframe(
        pd.DataFrame(
            [
                {first_column: str(label), "Value": str(value)}
                for label, value in rows
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_codon_workflow_guide() -> None:
    steps = [
        ("1. DNA CDS input", "Paste or load a coding sequence."),
        ("2. Host table", "Select the expression host context."),
        ("3. Generate preview", "Run the local codon usage preview."),
        ("4. Preview/readback output", "Review metrics, notes, and sequence readback."),
    ]
    cols = st.columns(4)
    for col, (title, body) in zip(cols, steps):
        with col:
            st.markdown(f"**{title}**")
            st.caption(body)


def _render_codon_boundary_details() -> None:
    with st.expander("Detailed boundary and limitations", expanded=False):
        st.markdown(
            "- " + CODON_USAGE_PREVIEW_CONTEXT_COPY + "\n"
            "- " + CODON_USAGE_STATUS_RECORD_COPY + "\n"
            "- The page does not predict expression, yield, or experimental success.\n"
            "- The page does not provide wet-lab protocols and does not replace expert/company review.\n"
            "- Review outputs before using them as design support."
        )


def _format_codon_preview_error(result: dict | None) -> str:
    payload = result if isinstance(result, dict) else {}
    error = str(payload.get("error") or "").strip()
    if not error:
        return "No detailed error was returned by the local codon usage preview checks."
    return error


def _render_codon_empty_state(seq_len: int, host: str) -> None:
    st.info("No codon usage preview yet. Enter a sequence to generate a preview.")
    st.caption(CODON_USAGE_EMPTY_STATE_COPY)
    _render_compact_review_rows(
        [
            ("Input length", f"{seq_len:,} bp"),
            ("Selected host table", host or "Not selected"),
            ("Preview status", "Not generated"),
        ],
        first_column="Current input",
    )
    st.caption("Workflow: DNA CDS input -> host table -> generate preview -> preview/readback output.")


def _render_codon_error_state(result: dict | None) -> None:
    st.error("Codon usage preview could not be generated.")
    st.caption(CODON_USAGE_ERROR_CONTEXT_COPY)
    with st.expander("Review-context error detail", expanded=False):
        st.code(_format_codon_preview_error(result), language="text")


def _codon_status_readback_rows(host: str) -> list[tuple[str, str]]:
    return [
        ("Original CDS source", "User-provided or Wizard-loaded CDS"),
        ("Codon optimized?", "Not claimed by BioDesign Studio"),
        ("Preview sequence provider", "Local Codon Usage Preview"),
        ("Target expression system / host context for review", host or "Not recorded"),
        ("Sequence verification status", "Documentation checks only; not experimental validation"),
        ("Manual/company review cue", "Required before downstream biological decisions"),
    ]


def _codon_table_metadata(host: str) -> dict:
    try:
        from core.codon_optimizer import get_codon_table_metadata
        return get_codon_table_metadata(host)
    except Exception:
        return {
            "table_id": "codon_usage_metadata_unavailable",
            "host_label": host or "Not recorded",
            "organism_or_scope": "Not recorded",
            "source_note": "Table provenance metadata could not be loaded for this local review.",
            "version_or_date_note": "Not recorded",
            "provenance_status": "local_reference_only",
            "draft_use_status": "not_enabled_for_rewrite",
            "limitation_note": "Use as documentation-only codon usage context; manual review required.",
            "documentation_review_note": "Provenance review is required before future codon draft use.",
            "manual_review_required": True,
        }


def _codon_table_provenance_rows(host: str) -> list[tuple[str, str]]:
    metadata = _codon_table_metadata(host)
    return [
        ("Selected codon usage table", metadata.get("host_label") or host or "Not recorded"),
        ("Table ID", metadata.get("table_id") or "Not recorded"),
        ("Organism or scope", metadata.get("organism_or_scope") or "Not recorded"),
        ("Source/provenance note", metadata.get("source_note") or "Not recorded"),
        ("Version/date note", metadata.get("version_or_date_note") or "Not recorded"),
        ("Provenance status", metadata.get("provenance_status") or "Not recorded"),
        ("Future rewrite draft status", metadata.get("draft_use_status") or "Not recorded"),
        ("Limitation note", metadata.get("limitation_note") or "Not recorded"),
        ("Documentation review note", metadata.get("documentation_review_note") or "Not recorded"),
        ("Manual review required", "Yes" if metadata.get("manual_review_required") else "Not recorded"),
    ]


def _render_codon_table_provenance_readback(host: str) -> None:
    st.markdown("#### Codon table provenance readback")
    st.caption(
        "Selected table metadata is shown for documentation review only. "
        "Incomplete provenance requires manual/company review before any future codon adaptation draft or rewrite preview."
    )
    _render_compact_review_rows(_codon_table_provenance_rows(host), first_column="Provenance item")


def _render_codon_status_readback(host: str) -> None:
    st.markdown("#### Codon status readback")
    st.caption(CODON_USAGE_STATUS_READBACK_HELPER_COPY)
    _render_compact_review_rows(_codon_status_readback_rows(host), first_column="Readback item")


def _build_codon_draft_metrics_payload(raw_cds: str, host: str | None) -> dict:
    """Build metrics-only readback without invoking rewrite-capable UI paths."""
    try:
        from core.codon_draft_metrics import build_codon_draft_metrics
        return build_codon_draft_metrics(raw_cds, host or None)
    except Exception as exc:
        return {
            "status": "metrics_unavailable",
            "metrics_only_status": "metrics_unavailable",
            "cds_length_review": {
                "nucleotide_length": 0,
                "codon_count": 0,
                "length_multiple_of_3": False,
                "length_status": "manual_review_required",
            },
            "start_stop_review": {
                "start_codon_status": "manual_review_required",
                "terminal_stop_codon_status": "manual_review_required",
                "internal_stop_codon_count": 0,
            },
            "base_composition_review": {
                "ambiguous_or_invalid_base_count": 0,
                "gc_percentage": 0.0,
            },
            "codon_usage_review": {
                "rare_codon_count": 0,
                "rare_codon_cluster_count": 0,
                "selected_table_key": host or "not_selected",
            },
            "table_provenance": {
                "host_label": host or "No codon table selected",
                "provenance_status": "codon table provenance unavailable",
                "draft_use_status": "not_enabled_for_rewrite",
                "manual_review_required": True,
                "source_note": f"Codon draft metrics readback is unavailable: {exc}",
            },
            "review_flags": ["metrics_unavailable"],
            "boundary": {"manual_review_required": True},
        }


def _codon_draft_metrics_rows(metrics: dict, raw_cds: str = "", host: str | None = None) -> list[tuple[str, str]]:
    length = metrics.get("cds_length_review") or {}
    start_stop = metrics.get("start_stop_review") or {}
    composition = metrics.get("base_composition_review") or {}
    usage = metrics.get("codon_usage_review") or {}
    provenance = metrics.get("table_provenance") or {}
    flags = metrics.get("review_flags") or []

    empty_state = "no CDS entered" if not _clean(raw_cds or "") else "CDS entered for review"
    invalid_count = int(composition.get("ambiguous_or_invalid_base_count") or 0)
    invalid_state = "invalid/ambiguous CDS" if invalid_count else "no invalid/ambiguous bases detected"
    table_state = provenance.get("host_label") or usage.get("selected_table_key") or host or "no codon table selected"
    provenance_status = provenance.get("provenance_status") or "codon table provenance unavailable"
    source_note = provenance.get("source_note") or "codon table provenance unavailable"

    return [
        ("Metrics-only status", str(metrics.get("metrics_only_status") or "review_metrics_only")),
        ("Readback boundary", "review metrics only; preview-only; manual review required"),
        ("Sequence rewrite output", "not a sequence rewrite"),
        ("Expression prediction output", "not an expression prediction"),
        ("CDS entry state", empty_state),
        ("CDS base review", invalid_state),
        ("Nucleotide length", str(length.get("nucleotide_length", 0))),
        ("Codon count", str(length.get("codon_count", 0))),
        ("Multiple-of-3 status", str(length.get("length_status") or "manual_review_required")),
        ("Start codon status", str(start_stop.get("start_codon_status") or "manual_review_required")),
        ("Terminal stop codon status", str(start_stop.get("terminal_stop_codon_status") or "manual_review_required")),
        ("Internal stop codon count", str(start_stop.get("internal_stop_codon_count", 0))),
        ("Invalid/ambiguous base count", str(invalid_count)),
        ("GC percentage", f"{float(composition.get('gc_percentage') or 0.0):.2f}%"),
        ("Rare codon count", str(usage.get("rare_codon_count", 0))),
        ("Rare codon cluster count", str(usage.get("rare_codon_cluster_count", 0))),
        ("Selected codon usage table", str(table_state or "no codon table selected")),
        ("Codon table provenance/source status", str(provenance_status)),
        ("Codon table source note", str(source_note)),
        ("Manual review cue", "manual review required"),
        ("Review flags", ", ".join(flags) if flags else "none"),
    ]


def _render_codon_draft_metrics_readback(raw_cds: str, host: str | None) -> None:
    st.markdown("#### Codon draft metrics")
    st.caption(CODON_DRAFT_METRICS_HELPER_COPY)
    metrics = _build_codon_draft_metrics_payload(raw_cds, host)
    _render_compact_review_rows(
        _codon_draft_metrics_rows(metrics, raw_cds=raw_cds, host=host),
        first_column="Draft metric",
    )


def _wizard_seq() -> str:
    """Read original_seq from the active DesignSession, or empty string."""
    try:
        from core.design_session import SessionController
        return (SessionController().get().original_seq or "").strip()
    except Exception:
        return ""


def _hosts() -> list:
    """Canonical host list from the core optimizer."""
    try:
        from core.codon_optimizer import CODON_TABLES
        if CODON_TABLES:
            return list(CODON_TABLES.keys())
    except Exception:
        pass
    return ["E.coli", "Yeast", "Human", "Rice", "Maize", "Arabidopsis", "Tobacco", "Agrobacterium"]


def _optimize(sequence: str, host: str) -> dict:
    """Delegate to cached, constraint-aware CDS optimizer API."""
    return _optimize_cached(sequence, host)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=256)
def _optimize_cached(sequence: str, host: str) -> dict:
    """Cache repeated optimization tasks for high-throughput workloads."""
    try:
        from core.codon_optimizer import (
            analyze_sequence_constraints,
            optimize_cds_sequence,
            validate_cds_sequence,
        )

        validation = validate_cds_sequence(sequence, host)
        if not validation.get("success"):
            return {
                "success": False,
                "error": "\n".join(validation.get("errors") or ["CDS validation failed."]),
                "validation": validation,
            }

        constraints_before = analyze_sequence_constraints(sequence, host)
        optimized = optimize_cds_sequence(sequence, host)
        if not optimized.get("success"):
            errors = optimized.get("errors") or ["Codon optimization failed."]
            return {
                "success": False,
                "error": "\n".join(errors),
                "validation": validation,
                "constraints_before": constraints_before,
                "result": optimized,
            }

        optimized.setdefault("validation", validation)
        optimized.setdefault("constraints_before", constraints_before)
        return optimized
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(change_page=None) -> None:  # noqa: ARG001
    """Entry point called by app.py router."""

    # ── Header ───────────────────────────────────────────────────────────────
    st.title("Codon Usage Preview")
    st.caption("Candidate sequence documentation review helper for codon usage previews.")
    st.info(CODON_USAGE_VISIBLE_HELPER_COPY)
    st.markdown("#### Preview workflow")
    st.caption(
        "Input: DNA coding sequence and host table. "
        "Output: codon usage preview, diagnostics, preview/readback output, and a downloadable documentation review report. "
        "Next step: paste or load a CDS, choose the host context, then generate a local preview."
    )
    _render_codon_workflow_guide()
    _render_codon_boundary_details()

    # ── Session state init ────────────────────────────────────────────────────
    host_list = _hosts()
    wseq = _wizard_seq()

    if "co_sequence" not in st.session_state:
        st.session_state["co_sequence"] = wseq
    if "co_host" not in st.session_state:
        st.session_state["co_host"] = host_list[0]
    if "co_result" not in st.session_state:
        st.session_state["co_result"] = None

    # ── Wizard sequence notice ────────────────────────────────────────────────
    if wseq and _clean(wseq) != _clean(st.session_state.get("co_sequence", "")):
        st.info(
            f"An active wizard sequence is available ({len(wseq)} bp). "
            "Click below to load it into this local codon usage preview helper."
        )

    # ── Input layout ─────────────────────────────────────────────────────────
    left, right = st.columns([2, 1], gap="large")

    with left:
        seq_input = st.text_area(
            label="DNA Coding Sequence",
            value=st.session_state["co_sequence"],
            height=190,
            placeholder="Paste a DNA coding sequence (ATCG, at least 30 bp). FASTA format is supported.",
            key="co_seq_textarea",
        )
        st.session_state["co_sequence"] = seq_input

        if wseq:
            if st.button("↑ Load from Expression Wizard", key="co_load_wizard"):
                st.session_state["co_sequence"] = wseq
                st.session_state["co_result"] = None
                st.rerun()

    with right:
        cur_host = st.session_state["co_host"]
        h_idx = host_list.index(cur_host) if cur_host in host_list else 0
        selected_host = st.selectbox(
            label="Expression Host",
            options=host_list,
            index=h_idx,
            key="co_host_select",
        )
        st.session_state["co_host"] = selected_host

        cleaned = _clean(seq_input)
        seq_len = len(cleaned)
        in_frame = seq_len >= 30 and seq_len % 3 == 0
        gc_now = _gc(cleaned) if seq_len > 0 else 0.0

        _render_compact_review_rows(
            [
                ("Length", f"{seq_len:,} bp"),
                ("GC Content", f"{gc_now}%"),
                ("Reading Frame", "In-frame CDS detected" if in_frame else "Not yet in frame"),
            ],
            first_column="Input check",
        )

        run_disabled = seq_len < 30
        optimize_clicked = st.button(
            "Generate Codon Usage Preview",
            key="co_run",
            type="primary",
            use_container_width=True,
            disabled=run_disabled,
            help="Paste a DNA coding sequence of at least 30 bp before generating a computational preview." if run_disabled else "Generate a local codon usage computational preview for documentation review.",
        )
        if run_disabled:
            st.caption("Enter a DNA coding sequence of at least 30 bp to generate a computational preview.")

    _render_codon_draft_metrics_readback(cleaned, selected_host)
    _render_codon_table_provenance_readback(selected_host)

    # ── Run ───────────────────────────────────────────────────────────────────
    if optimize_clicked and seq_len >= 30:
        with st.spinner("Generating codon usage preview..."):
            st.session_state["co_result"] = _optimize(cleaned, selected_host)

    # ── Empty state ───────────────────────────────────────────────────────────
    result = st.session_state.get("co_result")
    if result is None:
        _render_codon_empty_state(seq_len, selected_host)
        return

    st.divider()

    # ── Error ─────────────────────────────────────────────────────────────────
    if not result.get("success"):
        _render_codon_error_state(result)
        return

    # ── Extract result fields ─────────────────────────────────────────────────
    validation   = result.get("validation") or {}
    before_diag  = (result.get("before") or {})
    after_diag   = (result.get("after") or {})
    opt_seq      = result.get("optimized_sequence", "")
    orig_dna     = result.get("input_sequence") or cleaned
    cai_before   = before_diag.get("cai", 0.0) or 0.0
    cai_after    = after_diag.get("cai", 0.0) or 0.0
    gc_before    = before_diag.get("gc_percent") if before_diag.get("gc_percent") is not None else _gc(orig_dna)
    gc_after     = after_diag.get("gc_percent") if after_diag.get("gc_percent") is not None else _gc(opt_seq)
    protein      = result.get("protein") or validation.get("protein", "")
    res_host     = result.get("host", selected_host)
    history      = result.get("history") or []
    before_forbidden_hits = before_diag.get("forbidden_hits") or []
    after_forbidden_hits = after_diag.get("forbidden_hits") or []
    before_repeat_hits = before_diag.get("repeat_hits") or []
    after_repeat_hits = after_diag.get("repeat_hits") or []
    before_gc_windows = before_diag.get("gc_window_hits") or []
    after_gc_windows = after_diag.get("gc_window_hits") or []
    before_rare_codons = before_diag.get("rare_codons") or []
    after_rare_codons = after_diag.get("rare_codons") or []
    codon_changes = len(history)
    table_metadata = _codon_table_metadata(res_host)
    change_impact = _build_change_impact_summary(history, before_diag, after_diag, res_host)
    protein_preserved = before_diag.get("protein", "") == after_diag.get("protein", "")
    forbidden_before = len(before_forbidden_hits)
    forbidden_after  = len(after_forbidden_hits)
    repeat_before    = len(before_repeat_hits)
    repeat_after     = len(after_repeat_hits)
    gc_outlier_before = len(before_gc_windows)
    gc_outlier_after  = len(after_gc_windows)
    before_rare_total, before_rare_unique, before_rare_pct = _build_rare_codon_summary(before_rare_codons)
    after_rare_total, after_rare_unique, after_rare_pct = _build_rare_codon_summary(after_rare_codons)
    unresolved_warnings = list(dict.fromkeys((validation.get("warnings") or []) + (result.get("warnings") or [])))

    if forbidden_after > 0:
        unresolved_warnings.append(f"{forbidden_after} forbidden motif constraint(s) remain in the candidate sequence preview.")
    if repeat_after > 0:
        unresolved_warnings.append(f"{repeat_after} repeat constraint(s) remain in the candidate sequence preview.")
    if gc_outlier_after > 0:
        unresolved_warnings.append(f"{gc_outlier_after} local GC outlier window(s) remain in the candidate sequence preview.")

    st.info(CODON_USAGE_RESULT_HELPER_COPY)
    _render_codon_status_readback(res_host)
    _render_codon_table_provenance_readback(res_host)

    with st.expander("Metric and constraint definitions", expanded=False):
        st.markdown(
            "- **CAI:** host/table-dependent codon adaptation score.\n"
            "- **GC%:** sequence composition metric.\n"
            "- **Rare codons:** codons uncommon for the selected host table.\n"
            "- **Forbidden motifs:** sequence motifs flagged by current constraints.\n"
            "- **Repeats:** repeated sequence patterns detected by existing checks.\n"
            "- **Local GC outliers:** windows with GC outside the configured review range."
        )

    # ── Metrics row ───────────────────────────────────────────────────────────
    st.markdown("#### Preview summary")
    st.caption(f"Host table for review: {res_host}")
    _render_compact_review_rows(
        [
            ("Review note", "Codon usage preview generated" if result.get("success") else "Flagged for review"),
            ("Codon Changes", str(codon_changes)),
            ("Preview CAI", f"{cai_after:.4f}" if cai_after else "n/a"),
            ("Preview CAI Delta", f"{(cai_after - cai_before):+.4f}" if cai_after or cai_before else "n/a"),
            ("Preview GC", f"{gc_after:.1f}%" if gc_after is not None else "n/a"),
            ("Preview GC Delta", f"{(gc_after - gc_before):+.1f}%" if gc_before is not None and gc_after is not None else "n/a"),
            ("Protein Preserved", "Yes" if protein_preserved else "No"),
            ("Forbidden Sites", f"{forbidden_after} ({forbidden_after - forbidden_before:+d})"),
            ("Repeat Issues", f"{repeat_after} ({repeat_after - repeat_before:+d})"),
            ("Local GC Outliers", f"{gc_outlier_after} ({gc_outlier_after - gc_outlier_before:+d})"),
        ],
        first_column="Summary item",
    )

    # ── Diagnostic banners ───────────────────────────────────────────────────
    validation_errors = validation.get("errors") or []
    validation_warnings = validation.get("warnings") or []

    st.markdown("#### Codon usage review notes")
    if validation_errors:
        st.error("Input review notes:\n- " + "\n- ".join(validation_errors))
    elif validation_warnings:
        st.warning("Input review notes:\n- " + "\n- ".join(validation_warnings))
    else:
        st.info("No flagged issue: input CDS checks returned no review notes.")

    _render_compact_review_rows(
        [
            ("Protein Length", f"{len(protein)} aa" if protein else "0 aa"),
            ("Terminal Stop Codon", "Yes" if validation.get("has_terminal_stop") else "No"),
            ("Rare Codons", f"{after_rare_total} ({after_rare_total - before_rare_total:+d})"),
            ("Rare Codon Share", f"{after_rare_pct:.2f}% ({after_rare_pct - before_rare_pct:+.2f}%)"),
        ],
        first_column="Review note",
    )

    # ── CAI comparison banner ────────────────────────────────────────────────
    if cai_before > 0 and cai_after > 0:
        pct = round((cai_after - cai_before) / cai_before * 100, 1)
        sign  = "+" if pct >= 0 else ""
        message = (
            f"CAI preview changed from {cai_before:.4f} to {cai_after:.4f}; "
            f"relative change {sign}{pct}%."
        )
        if pct >= 0:
            st.info(message)
        else:
            st.warning(message)

    # ── Tabs: Sequence | Constraints | Summary ────────────────────────────────
    tab_seq, tab_constraints, tab_summary = st.tabs(
        ["Candidate sequence preview", "Codon usage review notes", "Documentation notes"]
    )

    with tab_seq:
        if opt_seq:
            st.caption(f"Length: {len(opt_seq)} bp; GC: {gc_after:.1f}%")
            st.code(opt_seq, language=None)
            st.download_button(
                label="Download Preview (.fasta)",
                data=f">codon_usage_preview_{res_host.replace(' ', '_')}\n{opt_seq}\n",
                file_name=f"codon_usage_preview_{res_host.replace(' ', '_').replace('.', '')}.fasta",
                mime="text/plain",
                key="co_download",
            )
            # ── Send To relay ─────────────────────────────────────────
            st.divider()
            st.caption(
                CODON_USAGE_HANDOFF_COPY
            )
            if st.button(
                "Send to Wizard Step 3 Candidate",
                key="co_send_to_step3_candidate",
                type="primary",
                use_container_width=True,
                help=CODON_USAGE_HANDOFF_COPY,
            ):
                from datetime import datetime
                from core.context_bridge import send_codon_step3_candidate

                send_codon_step3_candidate(
                    {
                        "source": "codon_optimizer",
                        "candidate_seq": opt_seq,
                        "input_sequence": orig_dna,
                        "optimizer_host": res_host,
                        "codon_report": result,
                        "sequence_length": len(opt_seq),
                        "gc_percent": gc_after,
                        "cai_before": cai_before,
                        "cai_after": cai_after,
                        "warnings": unresolved_warnings,
                        "protein_preserved": protein_preserved,
                        "created_at": datetime.utcnow().isoformat(),
                        "origin_page": "Codon Usage Preview",
                        "status": "available",
                    },
                    change_page=change_page,
                )
        else:
            st.info("No preview sequence was returned.")

    with tab_constraints:
        rows = [
            ("Input CAI", f"{cai_before:.4f}" if cai_before else "n/a"),
            ("Preview CAI", f"{cai_after:.4f}" if cai_after else "n/a"),
            ("Input GC", f"{gc_before:.1f}%" if gc_before is not None else "n/a"),
            ("Preview GC", f"{gc_after:.1f}%" if gc_after is not None else "n/a"),
            ("Protein Length", f"{len(protein)} aa" if protein else "n/a"),
            ("Terminal Stop Codon", "Yes" if validation.get("has_terminal_stop") else "No"),
            ("Input Rare Codons", f"{before_rare_total} total / {before_rare_unique} unique"),
            ("Preview Rare Codons", f"{after_rare_total} total / {after_rare_unique} unique"),
            ("Input Forbidden Sites", str(forbidden_before)),
            ("Preview Forbidden Sites", str(forbidden_after)),
            ("Input Repeat Issues", str(repeat_before)),
            ("Preview Repeat Issues", str(repeat_after)),
            ("Input Local GC Outliers", str(gc_outlier_before)),
            ("Preview Local GC Outliers", str(gc_outlier_after)),
            ("Codon Changes", str(codon_changes)),
            ("Protein Preserved", "Yes" if protein_preserved else "No"),
        ]
        _render_compact_review_rows(rows, first_column="Constraint item")

        validation_result_warnings = list(dict.fromkeys((validation.get("warnings") or []) + (result.get("warnings") or [])))
        post_optimization_warnings = []
        if forbidden_after > 0:
            post_optimization_warnings.append(f"{forbidden_after} forbidden motif constraint(s) remain in the candidate sequence preview.")
        if repeat_after > 0:
            post_optimization_warnings.append(f"{repeat_after} repeat constraint(s) remain in the candidate sequence preview.")
        if gc_outlier_after > 0:
            post_optimization_warnings.append(f"{gc_outlier_after} local GC outlier window(s) remain in the candidate sequence preview.")

        if validation_result_warnings:
            st.warning(
                "Review notes from existing checks:\n- "
                + "\n- ".join(validation_result_warnings)
            )
        else:
            st.info("No review notes were returned by existing checks.")

        if post_optimization_warnings:
            st.warning(
                "Unresolved codon-usage preview constraints:\n- "
                + "\n- ".join(post_optimization_warnings)
            )
        else:
            st.info("No unresolved codon-usage preview constraints detected.")

        rare_col_before, rare_col_after = st.columns(2)
        with rare_col_before:
            _show_hit_table(
                "Rare codons in input sequence",
                before_rare_codons,
                [
                    ("codon", "Codon"),
                    ("count", "Count"),
                    ("frequency", "Host Frequency"),
                    ("percentage", "Sequence %"),
                ],
                "No rare codons detected in the input sequence.",
            )
        with rare_col_after:
            _show_hit_table(
                "Rare codons in candidate preview sequence",
                after_rare_codons,
                [
                    ("codon", "Codon"),
                    ("count", "Count"),
                    ("frequency", "Host Frequency"),
                    ("percentage", "Sequence %"),
                ],
                "No rare codons detected in the preview sequence.",
            )

        forbidden_col_before, forbidden_col_after = st.columns(2)
        with forbidden_col_before:
            _show_hit_table(
                "Forbidden motifs in input sequence",
                before_forbidden_hits,
                [("motif", "Motif"), ("start", "Start"), ("end", "End")],
                "No forbidden motifs detected in the input sequence.",
            )
        with forbidden_col_after:
            _show_hit_table(
                "Forbidden motifs in candidate preview sequence",
                after_forbidden_hits,
                [("motif", "Motif"), ("start", "Start"), ("end", "End")],
                "No forbidden motifs detected in the preview sequence.",
            )

        repeat_col_before, repeat_col_after = st.columns(2)
        with repeat_col_before:
            _show_hit_table(
                "Repeat Hits Before Preview",
                before_repeat_hits,
                [("motif", "Motif"), ("length", "Length"), ("count", "Count"), ("positions", "Positions")],
                "No repeat hits detected in the input sequence.",
            )
        with repeat_col_after:
            _show_hit_table(
                "Repeat Hits After Preview",
                after_repeat_hits,
                [("motif", "Motif"), ("length", "Length"), ("count", "Count"), ("positions", "Positions")],
                "No repeat hits detected in the preview sequence.",
            )

        gc_col_before, gc_col_after = st.columns(2)
        with gc_col_before:
            _show_hit_table(
                "Local GC outliers in input sequence",
                before_gc_windows,
                [("start", "Start"), ("end", "End"), ("gc_percent", "GC %"), ("status", "Status")],
                "No local GC outlier windows detected in the input sequence.",
            )
        with gc_col_after:
            _show_hit_table(
                "Local GC outliers in candidate preview sequence",
                after_gc_windows,
                [("start", "Start"), ("end", "End"), ("gc_percent", "GC %"), ("status", "Status")],
                "No local GC outlier windows detected in the preview sequence.",
            )

    with tab_summary:
        rows = [
            ("Host", res_host),
            *_codon_table_provenance_rows(res_host),
            ("Preview Status", "Preview generated" if result.get("success") else "Needs review"),
            *_codon_status_readback_rows(res_host),
            ("Input Length", f"{len(orig_dna)} bp"),
            ("Preview Length", f"{len(opt_seq)} bp" if opt_seq else "n/a"),
            ("Input CAI", f"{cai_before:.4f}" if cai_before > 0 else "n/a"),
            ("Preview CAI", f"{cai_after:.4f}" if cai_after > 0 else "n/a"),
            ("Input GC", f"{gc_before:.1f}%" if gc_before is not None else "n/a"),
            ("Preview GC", f"{gc_after:.1f}%" if gc_after is not None else "n/a"),
            ("Codon Changes", str(codon_changes)),
            ("Protein Preserved", "Yes" if protein_preserved else "No"),
            ("Input Forbidden Sites", str(forbidden_before)),
            ("Preview Forbidden Sites", str(forbidden_after)),
            ("Input Repeat Issues", str(repeat_before)),
            ("Preview Repeat Issues", str(repeat_after)),
            ("Input Local GC Outliers", str(gc_outlier_before)),
            ("Preview Local GC Outliers", str(gc_outlier_after)),
            ("Protein Length (aa)", f"{len(protein)} aa" if protein else "n/a"),
        ]
        _render_compact_review_rows(rows, first_column="Documentation note")

        if unresolved_warnings:
            st.warning("Analysis report warnings and unresolved constraints:\n- " + "\n- ".join(unresolved_warnings))

        report_text = _build_optimization_report(
            host=res_host,
            table_metadata=table_metadata,
            input_sequence=orig_dna,
            optimized_sequence=opt_seq,
            cai_before=cai_before,
            cai_after=cai_after,
            gc_before=gc_before,
            gc_after=gc_after,
            codon_changes=codon_changes,
            protein_preserved=protein_preserved,
            rare_before=before_rare_total,
            rare_after=after_rare_total,
            forbidden_before=forbidden_before,
            forbidden_after=forbidden_after,
            repeat_before=repeat_before,
            repeat_after=repeat_after,
            gc_outlier_before=gc_outlier_before,
            gc_outlier_after=gc_outlier_after,
            unresolved_warnings=unresolved_warnings,
        )
        st.download_button(
            label="Download Analysis Report (.txt)",
            data=report_text,
            file_name=f"codon_usage_preview_report_{res_host.replace(' ', '_').replace('.', '')}.txt",
            mime="text/plain",
            key="co_download_report",
            use_container_width=True,
        )

        impact_summary = change_impact.get("summary") or {}
        impact_rows = change_impact.get("rows") or []
        amino_rows = change_impact.get("by_amino_acid") or []
        effect_rows = change_impact.get("by_frequency_effect") or []

        with st.expander("Change Impact", expanded=False):
            if impact_rows:
                _render_compact_review_rows(
                    [
                        ("CAI review-note category", str(impact_summary.get("cai_primary", 0))),
                        ("Constraint review-note category", str(impact_summary.get("constraint_driven", 0))),
                        ("Rare-codon review note", str(impact_summary.get("rare_codon_relief", 0))),
                    ],
                    first_column="Impact item",
                )

                st.caption(
                    "Edits from the CAI sweep are shown as CAI-driven review notes. Earlier passes are treated as likely constraint-driven review notes. "
                    "Rare-codon relief marks substitutions where a rare input codon was replaced by a non-rare preview codon."
                )

                freq_col, aa_col = st.columns(2)
                with freq_col:
                    st.markdown("**By codon-frequency effect**")
                    st.dataframe(pd.DataFrame(effect_rows), use_container_width=True, hide_index=True)
                with aa_col:
                    st.markdown("**By amino acid**")
                    st.dataframe(pd.DataFrame(amino_rows), use_container_width=True, hide_index=True)

                st.dataframe(pd.DataFrame(impact_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No codon substitutions were needed, so there is no change impact to summarize.")

        with st.expander("Codon Substitution History", expanded=False):
            if history:
                history_rows = []
                for entry in history:
                    history_rows.append(
                        {
                            "Review Stage": entry.get("pass"),
                            "Codon Index": entry.get("codon_index"),
                            "From": entry.get("from_codon"),
                            "To": entry.get("to_codon"),
                            "Review Metric Before": entry.get("score_before"),
                            "Review Metric After": entry.get("score_after"),
                        }
                    )
                st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No codon substitutions were needed for this sequence.")
