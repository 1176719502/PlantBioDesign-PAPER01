# -*- coding: utf-8 -*-
"""
views/CaseLibrary.py  --  Case Library standalone module.
No database, no AI, no network calls -- pure UI.
"""
from __future__ import annotations
import streamlit as st
from core.session_keys import SK

_CASES: list[dict] = [
    {
        "id": "ecoli_tf",
        "title": "E. coli Expression of a Plant Transcription Factor",
        "goal": "Produce a His-tagged plant MYB transcription factor in E. coli BL21(DE3) for in vitro DNA-binding and structural studies.",
        "host_display": "E. coli BL21(DE3)",
        "host_wizard": "E.coli BL21(DE3)",
        "organism": "Arabidopsis thaliana",
        "tag": "His6 tag (N-terminus)",
        "icon": "\U0001f9eb",
        "application": (
            "Recombinant expression of the plant MYB-family transcription factor AtMYB12 in E. coli BL21(DE3), "
            "for in vitro biochemical characterization, DNA-binding assays, and structural studies. "
            "T7-driven expression is recorded as reference context, while the N-terminal His tag documents a common purification context."
        ),
        "parts": [
            {"type": "Promoter",   "name": "T7 (pET series)",        "rationale": "Common prokaryotic promoter reference; IPTG-inducible context is documented for review."},
            {"type": "RBS",        "name": "Shine-Dalgarno B0034",   "rationale": "Consensus SD sequence (AAAGAGGAGAAA) with 7 bp spacing, recorded as ribosome-binding context."},
            {"type": "Tag",        "name": "His6 (N-terminus)",       "rationale": "N-terminal placement preserves TF C-terminal integrity and enables one-step Ni-NTA IMAC purification."},
            {"type": "Terminator", "name": "rrnB T1 Terminator",     "rationale": "Rho-independent; prevents readthrough into the vector backbone."},
            {"type": "Vector",     "name": "pET-28a or pET-SUMO",    "rationale": "Commonly documented T7 expression vectors; pET-SUMO is included as aggregation-context reference."},
            {"type": "Codon Usage Review",  "name": "Review note",               "rationale": "Plant codons such as AGA/AGG for Arg are rare in E. coli; record codon-usage context for review only."},
        ],
        "why": "Plant transcription factors are commonly documented in E. coli expression contexts for structural and biochemical studies; this case anchors codon-usage review to published examples.",
        "transferred": [
            "Gene name: AtMYB12",
            "Example CDS (96 bp demo fragment)",
            "Host: E.coli BL21(DE3)",
            "Tag: His6 (N-terminus)",
            "Promoter hint: T7 (pET vector series)",
            "Terminator hint: T7 terminator",
        ],
        "not_modelled": [
            "Full-length AtMYB12 CDS (demo fragment only)",
            "SUMO fusion tag (not supported by the current wizard tag scheme)",
            "Solubility screening / inclusion body prediction",
        ],
        "gene_name": "AtMYB12",
        "example_seq": "ATGGGAAGAGTTCCTTCACCTTCAGTTCCACCACCACCTTCAGTTCCTTCACCTTCAGTTCCACCACCACCTTCAGTTCCTTCACCTTCAGTTCCT",
    },
    {
        "id": "rice_hsa",
        "title": "Expression of Recombinant Human Serum Albumin in Rice Endosperm",
        "goal": "Document an rHSA expression design context in rice (Oryza sativa) endosperm for plant molecular pharming review.",
        "host_display": "Rice (Oryza sativa, endosperm)",
        "host_wizard": "Rice (O. sativa)",
        "organism": "Homo sapiens",
        "tag": "No tag",
        "icon": "\U0001f33e",
        "application": (
            "Use a seed-specific promoter such as Gt1 or GluB-1 to stably express recombinant human serum albumin (rHSA) in rice endosperm. "
            "The endosperm context, protein storage vacuoles, and extraction notes are documented as background only. "
            "This case does not assess manufacturing suitability or production conclusions."
        ),
        "parts": [
            {"type": "Promoter",      "name": "ZmUbi (default) / Gt1 or GluB-1",  "rationale": "ZmUbi is used as the wizard default; Gt1/GluB-1 endosperm context is documented but not yet supported by the wizard."},
            {"type": "Signal Peptide",     "name": "Native Gt1 signal peptide",                  "rationale": "Directs rHSA into the ER secretory pathway for accumulation in protein storage vacuoles; not yet modeled by the wizard."},
            {"type": "Tag",       "name": "None (native HSA)",                   "rationale": "Tagless context is recorded for documentation; no function or production conclusion is made."},
            {"type": "Terminator",     "name": "NOS terminator or Gt1 3' UTR",         "rationale": "NOS is a common standard in monocot and dicot binary vectors; Gt1 3' UTR is included as transcript-context documentation."},
            {"type": "Vector",       "name": "pCAMBIA1301 (Agrobacterium binary vector)",   "rationale": "Common rice vector reference; selection context is documentation-only."},
            {"type": "Codon Usage Review",  "name": "Review note",                            "rationale": "Many human CDS codons differ from rice usage patterns; record codon-usage context for review only."},
        ],
        "why": "Rice-derived rHSA (OsrHSA) is a documented molecular pharming example; this case is included as documentation context only.",
        "transferred": [
            "Gene name: HSA",
            "Example CDS (96 bp demo fragment)",
            "Host: Rice (O. sativa)",
            "Tag: No tag",
            "Promoter hint: Gt1 (glutelin, seed-specific) or GluB-1",
            "Terminator hint: NOS terminator or Gt1 3' UTR",
        ],
        "not_modelled": [
            "Full-length HSA CDS (demo fragment only)",
            "Gt1 signal peptide (not supported by the current wizard scheme)",
            "Seed-specific promoter behavior (the wizard uses constitutive ZmUbi by default for rice)",
            "Agrobacterium transformation protocol",
        ],
        "gene_name": "HSA",
        "example_seq": "ATGAAGTGGGTAACCTTTCTCCTCCTGTTCGCTTTTCTTTCAGCCTGGGTGGCAATCCCAGAGTTCAGAAACCCAGAAATGGAGCTGGAGAAGGAG",
    },
    {
        "id": "yeast_gla",
        "title": "Secreted Glucoamylase Expression in Saccharomyces cerevisiae",
        "goal": "Document an alpha-factor signal peptide context for His-tagged glucoamylase in yeast culture review records.",
        "host_display": "Saccharomyces cerevisiae (BY4741 / INVSc1)",
        "host_wizard": "S. cerevisiae",
        "organism": "Aspergillus niger",
        "tag": "His6 tag (C-terminus)",
        "icon": "\U0001f9eb",
        "application": (
            "Recombinant production of secreted glucoamylase (Gla1 / AMG) in Saccharomyces cerevisiae, "
            "for industrial starch saccharification and biofuel research context. The alpha-factor leader and GAL1 promoter are recorded as design documentation context only."
        ),
        "parts": [
            {"type": "Promoter",      "name": "GAL1 (galactose inducible)",           "rationale": "Activated by galactose and repressed by glucose; recorded as a yeast inducible-promoter reference."},
            {"type": "Signal Peptide",     "name": "alpha-factor leader (MFalpha1)",   "rationale": "The most widely used yeast secretion signal; Kex2 protease cleaves the leader in the Golgi, releasing the native N-terminus."},
            {"type": "Tag",       "name": "His6 (C-terminus)",                    "rationale": "C-terminal placement avoids interfering with signal-peptide cleavage; enables IMAC purification of secreted enzyme fractions."},
            {"type": "Terminator",     "name": "CYC1 Terminator",                     "rationale": "A commonly used yeast terminator; supports efficient 3' mRNA processing and transcript stability."},
            {"type": "Vector",       "name": "pYES2 (2-micron, URA3)",            "rationale": "Common GAL1-driven episomal vector reference; URA3 selection context is documented for review."},
            {"type": "Codon Usage Review",  "name": "Review note",                            "rationale": "Fungal codon usage differs from S. cerevisiae usage patterns; record codon-usage context for review only."},
        ],
        "why": "Alpha-factor plus GAL1 secretion expression is widely documented in yeast biotechnology literature and is included here as reference context.",
        "transferred": [
            "Gene name: glucoamylase",
            "Example CDS (96 bp demo fragment)",
            "Host: S. cerevisiae",
            "Tag: His6 (C-terminus)",
            "Promoter hint: GAL1 (strong, galactose inducible)",
            "Terminator hint: CYC1 terminator",
        ],
        "not_modelled": [
            "Full-length glucoamylase CDS (demo fragment only)",
            "Alpha-factor signal peptide (not supported by the current wizard scheme)",
            "Galactose induction protocol",
            "Pichia pastoris alternative workflow (not included in the current host list)",
        ],
        "gene_name": "glucoamylase",
        "example_seq": "ATGAGATTCCCATCTATTTTCACTGCTTTAGTCTTATTCGCATCAGCAGCAGCTGCAGCAGCAAGTGATGCAGGCAAACAAAGAGCATCAAGTGGT",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chip(label: str, bg: str, fg: str) -> str:
    return (
        f"<span style='background:{bg};color:{fg};"
        f"font-size:.68rem;font-weight:700;padding:2px 9px;"
        f"border-radius:20px;letter-spacing:.4px;"
        f"text-transform:uppercase'>{label}</span>"
    )


def _prefill_wizard(case: dict) -> None:
    """Write case context into DesignSession so Expression Wizard picks it up."""
    try:
        from core.design_session import DesignSession, SessionController
        from core.expression_frame_builder import list_supported_hosts
        wizard_host = case.get("host_wizard", "")
        try:
            supported = list_supported_hosts()
            if wizard_host not in supported:
                wizard_host = next(
                    (h for h in supported if h.lower().startswith(wizard_host.lower()[:6])),
                    "",
                )
        except Exception:
            pass
        parts = case.get("parts", [])
        elements: dict = {}
        for p in parts:
            if p["type"] == "Promoter":
                elements["promoter_name"] = p["name"]
            elif p["type"] == "RBS":
                elements["rbs_name"] = p["name"]
            elif p["type"] == "Terminator":
                elements["terminator_name"] = p["name"]
        ctrl = SessionController()
        ds = DesignSession(
            step=1,
            gene_name=case["gene_name"],
            original_seq=case["example_seq"],
            host=wizard_host,
            tag=case.get("tag", ""),
            elements=elements,
        )
        ctrl.save(ds)
        st.session_state[SK.ACTIVE_SEQ]  = case["example_seq"]
        st.session_state[SK.ACTIVE_NAME] = case.get("title", "Case Library")
    except Exception:
        st.session_state[SK.ACTIVE_SEQ]  = case["example_seq"]
        st.session_state[SK.ACTIVE_NAME] = case.get("title", "Case Library")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(change_page=None) -> None:
    """Entry point called by app.py router."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:6px'>"
        "<span style='font-size:1.45rem;font-weight:600;color:#111827'>Case Library</span>"
        "<span style='font-size:.72rem;font-weight:600;color:#15803d;"
        "background:#dcfce7;border:1px solid #bbf7d0;border-radius:4px;"
        "padding:2px 7px;letter-spacing:.4px'>Core</span>"
        "</div>"
        "<p style='color:#6b7280;font-size:.85rem;margin:0 0 1.6rem 0'>"
        "Provides single-gene expression examples that fit the 1.0 scope and can be loaded directly into the Expression Wizard as a design starting point."
        "</p>",
        unsafe_allow_html=True,
    )
    for case in _CASES:
        _render_case_card(case, change_page)
        st.markdown("<div style='margin-bottom:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='margin-top:1.5rem;padding:14px 18px;"
        "background:#f8f9fb;border:1px solid #e5e7eb;border-radius:8px;"
        "font-size:.78rem;color:#6b7280'>"
        "<strong style='color:#374151'>Current case library</strong> &mdash; "
        "Three example cases are currently available, covering single-gene expression starter designs across different hosts."
        "The cases will not modify your active wizard session until you click"
        "<em>Open in Expression Wizard</em>."
        "</div>",
        unsafe_allow_html=True,
    )


def _render_case_card(case: dict, change_page) -> None:
    """Render a single enriched case card."""
    with st.container():
        # ── Card header ──────────────────────────────────────────────────
        st.markdown(
            f"<div style='border:1.5px solid #e5e7eb;border-radius:12px;"
            f"padding:20px 26px 6px 26px;background:#ffffff'>"
            f"<div style='display:flex;align-items:flex-start;"
            f"justify-content:space-between;margin-bottom:6px'>"
            f"<div>"
            f"<div style='font-size:.75rem;color:#6b7280;margin-bottom:4px'>"
            f"{case['host_display']} &nbsp;&bull;&nbsp; "
            f"来源：<em>{case['organism']}</em></div>"
            f"<div style='font-size:1.1rem;font-weight:700;color:#111827;"
            f"letter-spacing:-.2px'>{case['title']}</div>"
            f"</div>"
            f"<div style='flex-shrink:0;margin-left:16px'>"
            + _chip("案例", "#f0f9ff", "#0369a1")
            + "</div></div>"
            # ── Expression goal banner ────────────────────────────────────
            f"<div style='background:#eff6ff;border-left:3px solid #3b82f6;"
            f"border-radius:0 6px 6px 0;padding:9px 13px;margin-bottom:14px;"
            f"font-size:.83rem;color:#1e40af;line-height:1.5'>"
            f"<strong>目标：</strong> {case['goal']}</div>"
            # ── Application summary ───────────────────────────────────────
            f"<div style='font-size:.84rem;color:#374151;line-height:1.6;"
            f"margin-bottom:16px'>{case['application']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── Parts table | Why + action ────────────────────────────────────
        col_parts, col_right = st.columns([3, 2], gap="large")

        with col_parts:
            st.markdown(
                "<div style='font-size:.78rem;font-weight:700;color:#374151;"
                "text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px'>"
                "推荐核心元件 &amp; 设计原理</div>",
                unsafe_allow_html=True,
            )
            for p in case["parts"]:
                st.markdown(
                    f"<div style='padding:7px 0;border-bottom:1px solid #f3f4f6'>"
                    f"<div style='display:flex;gap:8px;font-size:.82rem'>"
                    f"<span style='color:#6b7280;min-width:110px;flex-shrink:0'>{p['type']}</span>"
                    f"<span style='color:#111827;font-weight:600'>{p['name']}</span>"
                    f"</div>"
                    f"<div style='font-size:.76rem;color:#6b7280;margin-top:2px;padding-left:118px;"
                    f"line-height:1.45'>{p['rationale']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        with col_right:
            # Why this case matters
            st.markdown(
                "<div style='font-size:.78rem;font-weight:700;color:#374151;"
                "text-transform:uppercase;letter-spacing:.6px;margin-bottom:8px'>"
                "此案例的意义</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='background:#f0fdf4;border-left:3px solid #16a34a;"
                f"border-radius:0 6px 6px 0;padding:11px 13px;"
                f"font-size:.84rem;color:#374151;line-height:1.6'>"
                f"{case['why']}</div>",
                unsafe_allow_html=True,
            )

            # What gets transferred
            st.markdown(
                "<div style='font-size:.78rem;font-weight:700;color:#374151;"
                "text-transform:uppercase;letter-spacing:.6px;"
                "margin:14px 0 6px 0'>What will be transferred</div>",
                unsafe_allow_html=True,
            )
            items_html = "".join(
                f"<div style='font-size:.76rem;color:#374151;padding:2px 0'>"
                f"&#10003; {item}</div>"
                for item in case["transferred"]
            )
            st.markdown(
                f"<div style='background:#f8fafc;border:1px solid #e5e7eb;"
                f"border-radius:6px;padding:9px 12px'>{items_html}</div>",
                unsafe_allow_html=True,
            )

            # Not yet modelled
            st.markdown(
                "<div style='font-size:.78rem;font-weight:700;color:#374151;"
                "text-transform:uppercase;letter-spacing:.6px;"
                "margin:12px 0 6px 0'>暂未建模</div>",
                unsafe_allow_html=True,
            )
            deferred_html = "".join(
                f"<div style='font-size:.76rem;color:#9ca3af;padding:2px 0'>"
                f"&#8212; {item}</div>"
                for item in case["not_modelled"]
            )
            st.markdown(
                f"<div style='background:#fafafa;border:1px solid #e5e7eb;"
                f"border-radius:6px;padding:9px 12px'>{deferred_html}</div>",
                unsafe_allow_html=True,
            )

            # Action button
            st.markdown("<div style='margin-top:14px'></div>", unsafe_allow_html=True)
            if change_page is not None:
                if st.button(
                    "在表达向导中打开 →",
                    key=f"case_open_{case['id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    _prefill_wizard(case)
                    change_page("Expression Wizard")
            else:
                st.button(
                    "在表达向导中打开 →",
                    key=f"case_open_{case['id']}",
                    disabled=True,
                    use_container_width=True,
                )
            st.markdown(
                f"<div style='font-size:.72rem;color:#9ca3af;margin-top:5px'>"
                f"Preloads the <strong>{case['gene_name']}</strong> sequence, "
                f"host (<strong>{case['host_display']}</strong>)"
                f"及标签至表达向导。</div>",
                unsafe_allow_html=True,
            )
