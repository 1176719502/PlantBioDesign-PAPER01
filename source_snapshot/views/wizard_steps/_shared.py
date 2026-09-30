# -*- coding: utf-8 -*-
"""
views/wizard_steps/_shared.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared constants, CSS, and helper functions used by multiple wizard steps.
No Streamlit imports at module level -- only where required by functions.
"""
from __future__ import annotations

import html
import re
from typing import Any

from core.i18n import get_language as _get_language
from core.i18n import t as _t

# ---------------------------------------------------------------------------
# Step labels
# ---------------------------------------------------------------------------
_STEP_KEYS = [
    "wizard.step1.short",
    "wizard.step2.short",
    "wizard.step3.short",
    "wizard.step4.short",
    "wizard.step5.short",
    "wizard.step6.short",
]


def _steps() -> list[str]:
    return [_t(key) for key in _STEP_KEYS]


# ---------------------------------------------------------------------------
# Plant MVP context/readback skeleton
# ---------------------------------------------------------------------------

PLANT_MVP_TITLE = "Current first MVP: Plant recombinant protein / molecular farming"

PLANT_MVP_BOUNDARY_COPY = (
    "Expression Wizard remains documentation-only and pre-experiment review focused. "
    "It helps organize plant expression construct context, provenance, and review gaps. "
    "It does not create constructs for experimental use, wet-lab protocols, generated recoded sequences, "
    "plant-line validation, yield or outcome estimates, or biological recommendation decisions."
)

PLANT_MVP_WORKFLOW_CHECKLIST = [
    "Target product / protein",
    "Plant species / host context",
    "Target tissue / organ / expression compartment",
    "Expression mode",
    "Gene / CDS source provenance",
    "Plant promoter context",
    "5' UTR / Kozak-like context if applicable",
    "Signal peptide / transit peptide / subcellular targeting if applicable",
    "Terminator",
    "Selectable marker / reporter",
    "Vector / backbone context",
    "Transformation context as documentation-only context",
    "Evidence / provenance gaps",
    "Plant Design Review Package handoff",
]

PLANT_MVP_STEP_READBACK = {
    1: "Step 1: target product/protein and gene/CDS provenance.",
    2: "Step 2: plant species, target tissue/organ, expression mode, plant promoter, terminator, and selectable marker/reporter context.",
    3: "Step 3: read-only sequence and codon metrics; no sequence optimization output.",
    4: "Step 4: plant expression cassette context, signal peptide, transit peptide, subcellular targeting, and vector/backbone documentation.",
    5: "Step 5: plant-specific evidence/provenance gaps and manual review checks.",
    6: "Step 6: Plant Design Review Package direction and readback.",
}


def build_plant_mvp_context_model(current_step: int | None = None) -> dict[str, Any]:
    """Return the static plant MVP readback model without touching session state."""
    step_note = PLANT_MVP_STEP_READBACK.get(int(current_step or 0), "")
    return {
        "title": PLANT_MVP_TITLE,
        "boundary_copy": PLANT_MVP_BOUNDARY_COPY,
        "workflow_checklist": list(PLANT_MVP_WORKFLOW_CHECKLIST),
        "step_note": step_note,
    }


def render_plant_mvp_context(current_step: int | None = None) -> None:
    """Render a compact plant MVP context/readback section."""
    import streamlit as st

    model = build_plant_mvp_context_model(current_step)
    rows = "".join(
        "<div class='plant-mvp-chip'>"
        f"{html.escape(item)}"
        "</div>"
        for item in model["workflow_checklist"]
    )
    step_note = (
        f"<div class='plant-mvp-step'>{html.escape(model['step_note'])}</div>"
        if model.get("step_note")
        else ""
    )
    st.markdown(
        "<div class='plant-mvp-panel'>"
        f"<div class='plant-mvp-title'>{html.escape(model['title'])}</div>"
        f"<div class='plant-mvp-body'>{html.escape(model['boundary_copy'])}</div>"
        f"{step_note}"
        "<div class='plant-mvp-grid'>"
        f"{rows}"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Part colours for cassette diagram
# ---------------------------------------------------------------------------
_PART_COLORS = {
    "promoter":   "#1d4ed8",
    "Kozak":      "#b45309",
    "RBS":        "#b45309",
    "CDS":        "#15803d",
    "terminator": "#b91c1c",
}

# ---------------------------------------------------------------------------
# Global CSS (injected once by _step_indicator)
# ---------------------------------------------------------------------------
_GLOBAL_CSS = """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 0.5rem; max-width: 1180px; }
header { visibility: hidden; }
.stCodeBlock { border-radius: 8px; border: 1px solid #d0d7de; font-size: 0.80rem; }
.stSelectbox label, .stTextInput label, .stTextArea label,
.stRadio label, .stNumberInput label {
    font-size: 0.83rem; font-weight: 600; color: #374151;
}
[data-testid="stMetricValue"] { font-size: 1.05rem; font-weight: 700; }
div[data-testid="stHorizontalBlock"] .stButton button {
    border-radius: 7px; font-weight: 600; font-size: 0.84rem; padding: 0.38rem 1rem;
    white-space: normal; word-break: normal; overflow-wrap: normal; line-height: 1.25;
}
.cassette { display: flex; border-radius: 10px; overflow: hidden; margin: 12px 0; border: 1px solid #e2e6ef; }
.cpart { padding: 12px 8px; text-align: center; color: #fff; display: flex; flex-direction: column; justify-content: center; }
.cpart-type { font-size: .58rem; text-transform: uppercase; letter-spacing: .8px; opacity: .8; margin-bottom: 3px; }
.cpart-name { font-size: .78rem; font-weight: 700; font-family: 'IBM Plex Mono', monospace; word-break: break-all; }
.cpart-len  { font-size: .65rem; opacity: .7; margin-top: 2px; font-family: 'IBM Plex Mono', monospace; }
.mstrip { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
.mchip { background: #f8f9fb; border: 1px solid #e2e6ef; border-radius: 8px; padding: 7px 13px; min-width: 80px; }
.mchip-label { font-size: .62rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: .5px; }
.mchip-value { font-size: .92rem; font-weight: 700; color: #2563eb; font-family: 'IBM Plex Mono', monospace; margin-top: 2px; }
.issue-critical { background: #fef2f2; border-left: 4px solid #dc2626; border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 6px 0; font-size: .82rem; }
.issue-warning  { background: #fff7ed; border-left: 4px solid #d97706; border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 6px 0; font-size: .82rem; }
.issue-info     { background: #f0fdf4; border-left: 4px solid #16a34a; border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 6px 0; font-size: .82rem; }
.issue-title { font-weight: 700; margin-bottom: 4px; }
.issue-why   { color: #334155; margin-bottom: 3px; }
.issue-fix   { color: #2563eb; font-weight: 500; }
.wstep-hero { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); border: 1px solid #dbe7f5; border-radius: 14px; padding: 16px 18px; margin: 10px 0 16px; }
.wstep-kicker { font-size: .68rem; font-weight: 800; color: #2563eb; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 6px; }
.wstep-title { font-size: 1.15rem; font-weight: 800; color: #0f172a; margin-bottom: 4px; }
.wstep-body { font-size: .86rem; color: #475569; line-height: 1.55; }
.wstep-checklist { margin-top: 10px; color: #334155; font-size: .81rem; }
.wstep-checklist ul { margin: 0; padding-left: 1.1rem; }
.wstep-flow-strip { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 0 0 12px; }
.wstep-flow-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; }
.wstep-flow-label { font-size: .66rem; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px; }
.wstep-flow-body { font-size: .8rem; color: #475569; line-height: 1.45; }
@media (max-width: 720px) { .wstep-flow-strip { grid-template-columns: 1fr; } }
.wstep-section-label { font-size: .72rem; font-weight: 800; color: #64748b; text-transform: uppercase; letter-spacing: .08em; margin: 4px 0 8px; }
.wstep-panel { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; }
.wstep-status { border-radius: 12px; padding: 12px 14px; margin: 8px 0 14px; border: 1px solid #e2e8f0; background: #f8fafc; }
.wstep-status strong { display: block; margin-bottom: 4px; color: #0f172a; }
.wstep-status-ready { background: #f0fdf4; border-color: #bbf7d0; }
.wstep-status-warn { background: #fff7ed; border-color: #fed7aa; }
.wstep-status-info { background: #eff6ff; border-color: #bfdbfe; }
.wizard-identity-banner { position: sticky; top: 0.5rem; z-index: 20; display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px 16px; margin: 0 0 12px; background: rgba(255, 255, 255, 0.94); border: 1px solid #cbd5e1; border-radius: 14px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); backdrop-filter: blur(10px); }
.wizard-identity-eyebrow { font-size: .68rem; font-weight: 800; color: #2563eb; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px; }
.wizard-identity-title { font-size: 1.02rem; font-weight: 800; color: #0f172a; }
.wizard-identity-step { font-size: .82rem; font-weight: 700; color: #334155; text-align: right; white-space: nowrap; }
.plant-mvp-panel { background: #fbfdf8; border: 1px solid #dce8c8; border-radius: 12px; padding: 12px 14px; margin: 0 0 14px; }
.plant-mvp-title { font-size: .92rem; font-weight: 800; color: #1f3b2b; margin-bottom: 4px; }
.plant-mvp-body { font-size: .8rem; color: #3f513f; line-height: 1.45; }
.plant-mvp-step { font-size: .78rem; color: #284f36; font-weight: 700; margin-top: 8px; }
.plant-mvp-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 9px; }
.plant-mvp-chip { background: #ffffff; border: 1px solid #e2e8d6; border-radius: 6px; padding: 5px 8px; color: #334155; font-size: .74rem; line-height: 1.35; }
@media (max-width: 720px) { .plant-mvp-grid { grid-template-columns: 1fr; } }
</style>
"""

# ---------------------------------------------------------------------------
# Sequence helpers
# ---------------------------------------------------------------------------

def _clean_seq(raw: str) -> str:
    """Strip FASTA headers, remove non-ATCGN characters, uppercase."""
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith('>')]
    return re.sub(r'[^ATCGNatcgn]', '', ''.join(lines)).upper()


_PROTEIN_ONLY = frozenset('EFHIKLMPQRSVWYefhiklmpqrsvy')


def _check_dna_input(raw: str) -> tuple:
    """DNA input quality gate (runs on raw text BEFORE cleaning).

    Returns (ok: bool, error_message: str).
    """
    content = ''.join(
        ln for ln in raw.splitlines() if not ln.strip().startswith('>')
    )
    alpha = [c for c in content if c.isalpha()]
    if not alpha:
        return True, ''

    # Gate 1: protein-only amino acid letters?
    protein_chars = [c for c in alpha if c in _PROTEIN_ONLY]
    protein_ratio = len(protein_chars) / len(alpha)
    if protein_ratio >= 0.10:
        pct = int(protein_ratio * 100)
        return False, (
            f'Input looks like a protein / amino acid sequence, not DNA '
            f'({len(protein_chars)} amino-acid-only characters detected, {pct}% of input). '
            'Please paste a nucleotide (DNA) sequence.'
        )

    # Gate 2: ATCGN purity -- at least 85% of letters must be A/T/C/G/N
    atcgn = [c for c in alpha if c.upper() in 'ATCGN']
    atcgn_ratio = len(atcgn) / len(alpha)
    if atcgn_ratio < 0.85:
        pct = int(atcgn_ratio * 100)
        return False, (
            f'Input does not look like a valid DNA nucleotide sequence '
            f'(only {pct}% A/T/C/G/N characters detected). '
            'Please paste a nucleic acid sequence in FASTA or plain-text format.'
        )

    return True, ''


def _validate_cds_sequence(seq: str) -> list[str]:
    """Return CDS validation errors for a cleaned DNA sequence."""
    errors: list[str] = []

    if not seq:
        return ["DNA sequence is empty after cleaning. Please provide a valid CDS sequence."]

    invalid = sorted(set(seq) - set('ATCGN'))
    if invalid:
        errors.append(
            f"Invalid DNA characters detected: {', '.join(invalid)}. "
            "Only A, T, C, G, and N are allowed."
        )

    if 'N' in seq:
        errors.append(
            "Sequence contains N bases. Ambiguous bases are accepted for review, "
            "but cannot be confirmed as ready for downstream wizard steps."
        )

    if len(seq) % 3 != 0:
        errors.append("CDS length must be a multiple of 3.")

    if not seq.startswith('ATG'):
        errors.append(
            "Missing or incorrect start codon: CDS must start with ATG."
        )

    if len(seq) < 3 or seq[-3:] not in ('TAA', 'TAG', 'TGA'):
        errors.append(
            "Missing or incorrect stop codon: CDS must end with TAA, TAG, or TGA."
        )

    return errors


def _gc(seq: str) -> float:
    """Return GC percentage (0-100). Returns 0.0 for empty input."""
    return (seq.count('G') + seq.count('C')) / len(seq) * 100 if seq else 0.0


def _step_header(step: int, title: str, purpose: str, bullets: list[str] | None = None) -> None:
    """Render a consistent wizard step hero block."""
    import streamlit as st

    bullet_html = ""
    if bullets:
        items = "".join(f"<li>{item}</li>" for item in bullets)
        bullet_html = f"<div class='wstep-checklist'><ul>{items}</ul></div>"

    st.markdown(
        f"<div class='wstep-hero'>"
        f"<div class='wstep-kicker'>Step {step}</div>"
        f"<div class='wstep-title'>{title}</div>"
        f"<div class='wstep-body'>{purpose}</div>"
        f"{bullet_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_flow_strip(items: list[tuple[str, str]]) -> None:
    """Render a compact input/output strip for wizard steps."""
    import streamlit as st

    if not items:
        return

    cells = []
    for label, body in items:
        cells.append(
            "<div class='wstep-flow-item'>"
            f"<div class='wstep-flow-label'>{html.escape(str(label or ''))}</div>"
            f"<div class='wstep-flow-body'>{html.escape(str(body or ''))}</div>"
            "</div>"
        )

    st.markdown(f"<div class='wstep-flow-strip'>{''.join(cells)}</div>", unsafe_allow_html=True)


def _section_label(text: str) -> None:
    """Render a compact, consistent section label."""
    import streamlit as st

    st.markdown(
        f"<div class='wstep-section-label'>{text}</div>",
        unsafe_allow_html=True,
    )


def _status_panel(title: str, body: str, tone: str = "info") -> None:
    """Render a lightweight status block for empty/ready/warning states."""
    import streamlit as st

    tone_class = {
        "ready": "wstep-status-ready",
        "warn": "wstep-status-warn",
        "info": "wstep-status-info",
    }.get(tone, "wstep-status-info")

    st.markdown(
        f"<div class='wstep-status {tone_class}'>"
        f"<strong>{title}</strong>"
        f"<div>{body}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _summary_card_style(level: str) -> tuple[str, str, str]:
    styles = {
        "ready": ("#ecfdf5", "#15803d", "#bbf7d0"),
        "review": ("#fffbeb", "#b45309", "#fde68a"),
        "warn": ("#fef2f2", "#b91c1c", "#fecaca"),
        "neutral": ("#f8fafc", "#334155", "#e2e8f0"),
    }
    return styles.get(level, styles["neutral"])


def _render_summary_card_header(title: str, status_text: str, level: str) -> None:
    import streamlit as st

    bg, text, border = _summary_card_style(level)
    st.markdown(
        f"<div style='background:{bg};border:1px solid {border};border-radius:10px;padding:10px 12px;margin-bottom:10px'>"
        f"<div style='font-size:.78rem;font-weight:700;color:{text};margin-bottom:6px'>{title}</div>"
        f"<div style='display:inline-block;background:#ffffffaa;border:1px solid {border};border-radius:999px;padding:2px 8px;font-size:.74rem;color:{text};font-weight:600'>{status_text}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_report_preview_summary_cards(report_presenter: dict[str, Any], step_keys: list[str] | None = None, heading: str = "Report summary cards") -> None:
    """Render reusable report summary cards for Step 4/5/6 previews."""
    import streamlit as st

    all_cards = report_presenter.get("summary_cards") or []
    cards = [
        card for card in all_cards
        if not step_keys or card.get("step_key") in step_keys
    ]
    if not cards:
        return

    st.markdown(
        f"<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-top:14px;margin-bottom:8px'>{heading}</div>",
        unsafe_allow_html=True,
    )

    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            _render_summary_card_header(
                str(card.get("title") or "Summary"),
                str(card.get("status_text") or "Not set"),
                str(card.get("level") or "neutral"),
            )
            for metric in card.get("metrics") or []:
                st.metric(str(metric.get("label") or "Metric"), metric.get("value"))
            if card.get("caption"):
                st.caption(str(card["caption"]))


def render_report_preview_container(
    report_presenter: dict[str, Any],
    *,
    step_keys: list[str] | None = None,
    section_title: str = "Preview design report",
) -> None:
    """Render the shared Step 4/5/6 report preview container."""
    import streamlit as st

    overview_rows = report_presenter.get("overview_rows") or []
    alignment_rows = report_presenter.get("alignment_rows") or []
    download_rows = report_presenter.get("download_rows") or []
    sequence_verification = report_presenter.get("sequence_verification") or {}

    with st.expander(section_title, expanded=False):
        col_overview, col_alignment, col_download = st.columns([1, 1, 1], gap="medium")

        with col_overview:
            st.markdown(
                "<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-bottom:8px'>Overview</div>",
                unsafe_allow_html=True,
            )
            if overview_rows:
                for row in overview_rows:
                    st.markdown(
                        f"<div style='display:flex;justify-content:space-between;border-bottom:1px solid #f3f4f6;padding:4px 0;font-size:.82rem'><span style='color:#6b7280;font-weight:600'>{row.get('label', 'Item')}</span><span style='color:#111827;font-family:monospace'>{row.get('value', '—')}</span></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No overview data available.")

        with col_alignment:
            st.markdown(
                "<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-bottom:8px'>Alignment</div>",
                unsafe_allow_html=True,
            )
            if alignment_rows:
                try:
                    import pandas as pd

                    alignment_df = pd.DataFrame(alignment_rows)
                    st.dataframe(alignment_df, use_container_width=True, hide_index=True)
                except Exception:
                    for row in alignment_rows:
                        st.write(row)
            else:
                st.caption("No alignment data available.")

        with col_download:
            st.markdown(
                "<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-bottom:8px'>Download availability</div>",
                unsafe_allow_html=True,
            )
            if download_rows:
                try:
                    import pandas as pd

                    download_df = pd.DataFrame(download_rows)
                    st.dataframe(download_df, use_container_width=True, hide_index=True)
                except Exception:
                    for row in download_rows:
                        st.write(row)
            else:
                st.caption("No download data available.")

        render_report_preview_summary_cards(report_presenter, step_keys=step_keys)

        st.markdown(
            "<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-top:14px;margin-bottom:8px'>Sequence Verification Summary</div>",
            unsafe_allow_html=True,
        )
        if sequence_verification.get("included"):
            if sequence_verification.get("message"):
                st.caption(str(sequence_verification["message"]))
            try:
                import pandas as pd

                verification_df = pd.DataFrame(sequence_verification.get("rows") or [])
                st.dataframe(verification_df, use_container_width=True, hide_index=True)
            except Exception:
                for row in sequence_verification.get("rows") or []:
                    st.write(row)
        else:
            st.caption(str(sequence_verification.get("message") or "No sequence verification result was attached to this report."))


def render_report_sequence_preview(report_presenter: dict[str, Any], heading: str = "Final construct sequence") -> None:
    """Render the shared final-sequence preview from the report presenter."""
    import streamlit as st

    sequence_preview = report_presenter.get("sequence_preview") or {}
    formatted = str(sequence_preview.get("formatted") or "").strip()
    if not formatted:
        return

    st.markdown(
        f"<div style='font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#6b7280;margin-top:14px;margin-bottom:6px'>{heading}</div>",
        unsafe_allow_html=True,
    )
    st.code(formatted, language=None)


def render_report_download_button(
    report_presenter: dict[str, Any],
    report_markdown: str,
    *,
    button_key: str,
) -> None:
    """Render the shared report download button from the report presenter."""
    import streamlit as st

    download_meta = report_presenter.get("report_download") or {}
    label = str(download_meta.get("label") or "Download design report (.md)")
    filename = str(download_meta.get("filename") or "construct_design_report.md")
    mime = str(download_meta.get("mime") or "text/markdown")
    help_text = download_meta.get("help")

    st.download_button(
        label=label,
        data=report_markdown.encode("utf-8"),
        file_name=filename,
        mime=mime,
        key=button_key,
        use_container_width=True,
        help=str(help_text) if help_text else None,
    )


def render_async_task_feedback(
    *,
    title: str,
    status: str,
    progress: int,
    detail: str,
    task_id: str = "",
    error_text: str = "",
) -> None:
    """Render a consistent async-task status panel with progress."""
    import streamlit as st

    safe_progress = max(0, min(100, int(progress)))
    normalized_status = str(status or "idle").strip().lower()
    tone = {
        "queued": "info",
        "started": "info",
        "deferred": "info",
        "finished": "ready",
        "failed": "warn",
        "not_found": "warn",
    }.get(normalized_status, "info")

    _status_panel(title, detail, tone=tone)
    st.progress(safe_progress, text=f"Status: {normalized_status or 'idle'}")
    if task_id:
        st.caption(f"Task ID: {task_id}")
    if error_text:
        st.error(error_text)


# ---------------------------------------------------------------------------
# Step indicator (sac.steps)
# ---------------------------------------------------------------------------

def _step_indicator_rows(step_names: list[str], per_row: int = 3) -> list[list[tuple[int, str]]]:
    """Return step indicator rows with stable one-based step indexes."""
    if per_row <= 0:
        per_row = len(step_names) or 1
    indexed_steps = list(enumerate(step_names, start=1))
    return [indexed_steps[i:i + per_row] for i in range(0, len(indexed_steps), per_row)]

def _wizard_identity_banner(current: int) -> None:
    """Render a persistent page-identity banner for the wizard."""
    import streamlit as st

    step_names = _steps()
    safe_index = max(0, min(len(step_names) - 1, current - 1))
    step_title = step_names[safe_index]
    st.markdown(
        "<div class='wizard-identity-banner'>"
        "<div>"
        f"<div class='wizard-identity-eyebrow'>{_t('wizard.identity.eyebrow')}</div>"
        f"<div class='wizard-identity-title'>{_t('wizard.identity.title')}</div>"
        "</div>"
        f"<div class='wizard-identity-step'>{_t('wizard.step_of', step=safe_index + 1, total=len(step_names))}<br/>{step_title}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _step_indicator(current: int, ctrl=None) -> None:
    import streamlit as st

    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    step_names = _steps()
    safe_index = max(0, min(len(step_names) - 1, current - 1))
    progress_value = (safe_index + 1) / len(step_names)
    st.progress(progress_value, text=f"{_t('wizard.step_of', step=safe_index + 1, total=len(step_names))}: {step_names[safe_index]}")

    for row in _step_indicator_rows(step_names, per_row=3):
        columns = st.columns(len(row))
        for column, (index, label) in zip(columns, row):
            with column:
                is_current = index == current
                is_completed = index < current
                button_type = "primary" if is_current else "secondary"
                button_label = f"{index}. {label}"
                disabled = ctrl is None or (not is_completed and not is_current)
                if st.button(
                    button_label,
                    key=f"wizard_step_indicator_{index}",
                    use_container_width=True,
                    type=button_type,
                    disabled=disabled,
                ):
                    ctrl.jump(index)

    # The indicator intentionally uses two rows for six steps. This keeps long
    # labels readable in the 960px laptop viewport without changing step state.
    if len(step_names) > 3:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Gate hint strings (used by _nav_bar)
# ---------------------------------------------------------------------------

def _gate_hint(step: int) -> str:
    """Human-readable hint shown on the disabled Next button tooltip."""
    return {
        1: _t('wizard.gate.step1'),
        2: _t('wizard.gate.step2'),
        3: _t('wizard.gate.step3'),
        4: _t('wizard.gate.step4'),
        5: _t('wizard.gate.step5'),
    }.get(step, '')


# ---------------------------------------------------------------------------
# Navigation bar
# ---------------------------------------------------------------------------

def _nav_bar(ctrl) -> None:
    """Render Back / Next navigation row."""
    import streamlit as st
    step = ctrl.step
    ok   = ctrl.can_advance
    st.divider()
    col_prev, _, col_next = st.columns([2, 3, 2])
    with col_prev:
        if step > 1:
            if st.button(_t('wizard.nav.previous'), key=f'wf_back_{step}', use_container_width=True):
                ctrl.retreat()
    with col_next:
        show_global_next = step in (3, 4, 5)
        if show_global_next:
            if st.button(_t('wizard.nav.next'), key=f'wf_next_{step}',
                         type='primary', use_container_width=True,
                         disabled=not ok,
                         help='' if ok else _gate_hint(step)):
                ctrl.advance()
        elif step == 6:
            if st.button(_t('wizard.nav.restart'), key='wf_restart', use_container_width=True):
                ctrl.reset()


# ---------------------------------------------------------------------------
# Cassette diagram
# ---------------------------------------------------------------------------

def _cassette(parts) -> None:
    import streamlit as st
    total = sum(len(p.get('seq') or 'N') for p in parts) or 1
    segs  = []
    for p in parts:
        seq   = p.get('seq') or 'N'
        color = _PART_COLORS.get(p['type'], '#374151')
        pct   = max(8, int(len(seq) / total * 100))
        segs.append(
            f'<div class="cpart" style="background:{color};width:{pct}%">'
            f'<div class="cpart-type">{p["type"]}</div>'
            f'<div class="cpart-name">{p["name"][:16]}</div>'
            f'<div class="cpart-len">{len(seq)} bp</div>'
            '</div>'
        )
    st.markdown('<div class="cassette">' + ''.join(segs) + '</div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Issue display
# ---------------------------------------------------------------------------

def _show_issues(issues) -> None:
    import streamlit as st
    for iss in issues:
        sev  = iss.get('severity', 'info')
        icon = {'critical': '&#128308;', 'warning': '&#9888;&#65039;',
                'info': '&#9989;'}.get(sev, 'i')
        clr  = {'critical': '#dc2626', 'warning': '#d97706',
                'info': '#16a34a'}.get(sev, '#64748b')
        st.markdown(
            f'<div class="issue-{sev}">'
            f'<div class="issue-title" style="color:{clr}">{icon} {iss["title"]}</div>'
            f'<div class="issue-why"><b>Reason:</b> {iss["why"]}</div>'
            f'<div class="issue-fix"><b>Suggestion:</b> {iss["fix"]}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
