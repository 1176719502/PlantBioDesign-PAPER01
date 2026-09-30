"""Sequence Tools basic analysis page."""
from __future__ import annotations

import streamlit as st

from core.i18n import t as _t
from core.session_keys import SK
from services.sequence_inspector import SequenceInspectionResult, inspect_sequence
from services.sequence_verification_service import run_sequence_verification
from services.blast_result_import_service import build_blast_import_payload
from services.local_registry_verification_adapter import LocalRegistryVerificationAdapter

from utils.sequence_utils import clean_sequence, compute_gc, validate_sequence
from views.tool_typography import inject_tool_typography_css, render_boundary_note, render_tool_intro

_DEFAULT_SEQ = (
    "ATGAAAGCAATTTTCGTACTGAAAGGTTTTGTTGGTTTTCTTGCCATTTCCGGCATGGCAGGAAAGAAC"
    "GGAGATCGCCATTATGGCCGCAGAATTTGAACGTGCTGGACGTCGCGTTGATGTTTCTGCAGGTACAG"
    "ATGAAAGCAATTTTCGTACTGAAAGGTTTTGTTGGTTTTCTTGCCATTTCCGGCATGGCAGGAAAGAAC"
)

_CSS = """
<style>
[data-testid="stMetric"]{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 16px!important}
[data-testid="stMetricLabel"] p{font-size:.68rem!important;font-weight:800!important;text-transform:uppercase;letter-spacing:.7px;color:#64748b!important}
[data-testid="stMetricValue"]{font-size:1.2rem!important;font-weight:800!important;color:#0f172a!important;line-height:1.15!important}
.seq-block{background:#f8fafc;border:1px solid #dbe3ec;border-radius:12px;padding:14px 16px;font-family:'JetBrains Mono','Fira Code',monospace;font-size:.72rem;line-height:1.9;overflow:auto;max-height:480px;white-space:pre-wrap;word-break:break-all;color:#1e293b}
.page-hero{background:linear-gradient(135deg,#f8fbff 0%,#eef5ff 100%);border:1px solid #dbeafe;border-radius:16px;padding:18px 20px;margin-bottom:16px}
.input-card{background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);border:1px solid #c7dcff;box-shadow:0 10px 24px rgba(37,99,235,.08);border-radius:16px;padding:18px;margin-bottom:14px}
.result-card{background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:16px}
.placeholder-card{background:#f8fafc;border:1px dashed #cbd5e1;border-radius:16px;padding:28px 22px;text-align:center;color:#475569}
.inline-note{background:#eff6ff;border:1px solid #bfdbfe;color:#1d4ed8;border-radius:12px;padding:10px 12px;font-size:.84rem;margin-bottom:12px}
.kicker{font-size:.72rem;font-weight:800;color:#475569;text-transform:uppercase;letter-spacing:.7px}
</style>
"""


_DISPLAY_TRUNCATION_MARKS = (".", "…", "⋯")
SEQUENCE_TOOLS_ERROR_KEY = "seq_tools_validation_error"
SEQUENCE_TOOLS_RAW_INPUT_KEY = "seq_tools_raw_input"
SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY = "seq_tools_analyzed_sequence_signature"
SEQUENCE_TOOLS_ANALYZED_TEXT_KEY = "seq_tools_analyzed_sequence_text"
SEQUENCE_TOOLS_STALE_MESSAGE = (
    "This analysis is stale because the current sequence input has changed since the last analysis. "
    "Run Analyze Sequence again before using this sequence in the Expression Wizard."
)
SEQUENCE_TOOLS_DISABLED_SEND_HELPER = "Use in Wizard is unavailable until the current input has been analyzed and has no review-blocking preflight notes."
SEQUENCE_TOOLS_NEEDS_REVIEW_MESSAGE = (
    "Needs Review: Review-blocking preflight signals remain. Revise the sequence and analyze again "
    "before sending it to the Expression Wizard."
)
SEQUENCE_TOOLS_DOCUMENTATION_CONTEXT_COPY = (
    "Local sequence inspection summary: documentation-only review context for sequence inspection. "
    "This is not validation, not prediction, not recommendation, not readiness approval, "
    "and not a wet-lab protocol."
)
SEQUENCE_TOOLS_HANDOFF_CONTEXT_COPY = (
    "Sending to Expression Wizard is a documentation handoff only. It pre-fills Step 1 for review; "
    "it is not validation, not prediction, not recommendation, not readiness approval, "
    "and not a wet-lab protocol."
)
SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY = "seq_tools_verification_result"
SEQUENCE_TOOLS_VERIFICATION_SIGNATURE_KEY = "seq_tools_verification_signature"
SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY = "seq_tools_verification_source"
SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE = "Local Parts Registry"
SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE = "Imported BLAST TSV"
SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY = "seq_tools_imported_blast_tsv"
SEQUENCE_TOOLS_PLACEHOLDER_SOURCE = "Placeholder adapter"
SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE = "Run Analyze Sequence to view composition details."
SEQUENCE_TOOLS_VERIFICATION_STALE_MESSAGE = "The stored verification result is stale because the current sequence changed. Run Verification again."
SEQUENCE_TOOLS_LOCAL_NO_HIT_MESSAGE = "No local similarity or containment hits were found by the selected verification source."
SEQUENCE_TOOLS_BLAST_NO_HIT_MESSAGE = "No valid BLAST hits were parsed from the imported TSV."
SEQUENCE_TOOLS_PLACEHOLDER_NO_HIT_MESSAGE = "No similarity hits are available because the placeholder verification adapter is unavailable."
SEQUENCE_TOOLS_UNAVAILABLE_MESSAGE = "The selected verification source is unavailable or the imported TSV could not be parsed. No external lookup was attempted."
SEQUENCE_TOOLS_VERIFICATION_EMPTY_MESSAGE = (
    "No verification result has been generated yet. Select a source and run Verification to add informational "
    "similarity evidence for documentation review."
)
SEQUENCE_TOOLS_VERIFICATION_SUMMARY_COPY = (
    "Verification summary is informational review context only. It does not change Sequence Inspector status, "
    "Expression Wizard validation, primer risk, or export recommendations."
)
SEQUENCE_VERIFICATION_DISCLAIMER = (
    "Sequence verification is informational only. It is documentation-only review context, not validation, "
    "not prediction, not recommendation, not readiness approval, and not a wet-lab protocol. "
    "It does not certify experimental readiness, does not change validation status, "
    "and does not override primer or export safety recommendations."
)


def _remove_display_truncation_marks(text: str) -> str:
    for mark in _DISPLAY_TRUNCATION_MARKS:
        text = text.replace(mark, "")
    return text


def _clean_input(raw: str) -> tuple[str, str | None]:
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">"):
            continue
        lines.append(_remove_display_truncation_marks(line))
    seq = clean_sequence("".join(lines))
    valid, msg = validate_sequence(seq)
    if not valid:
        return "", _t("sequence_tools.invalid_dna") if not seq else msg
    return seq, None


def _sequence_signature(raw: str) -> str:
    """Return the normalized sequence text used to detect stale preflight results."""
    return inspect_sequence(raw).sequence


def _is_analysis_stale(current_signature: str, analyzed_signature: str | None) -> bool:
    """Return True when the visible input no longer matches analyzed input."""
    return bool(analyzed_signature) and current_signature != analyzed_signature


def _can_use_analyzed_result(
    result: SequenceInspectionResult | None,
    current_signature: str,
    analyzed_signature: str | None,
) -> bool:
    """Return True only when current input matches a Ready analyzed result."""
    return bool(
        result
        and current_signature
        and analyzed_signature
        and current_signature == analyzed_signature
        and result.status == "Ready for Wizard"
    )


def _calc_mw(seq: str) -> float:
    weights = {"A": 313.21, "T": 304.19, "C": 289.18, "G": 329.21, "N": 308.95}
    return sum(weights.get(base, 308.95) for base in seq) - 61.96


def _get_orf_results(seq: str, min_len: int = 30):
    import pandas as pd
    from services.sequence_service import find_orfs

    raw = find_orfs(seq, min_len=min_len)
    df = raw.copy() if hasattr(raw, "empty") else pd.DataFrame(raw)
    if df.empty:
        return pd.DataFrame(columns=["Frame", "Start", "End", "Length (bp)", "Strand"])

    aliases = {
        "frame": "Frame",
        "start": "Start",
        "end": "End",
        "length": "Length (bp)",
        "length_bp": "Length (bp)",
        "length (bp)": "Length (bp)",
    }
    for src, dst in aliases.items():
        if src in df.columns and dst not in df.columns:
            df[dst] = df[src]
    if "Length (bp)" not in df.columns and {"Start", "End"}.issubset(df.columns):
        df["Length (bp)"] = df["End"] - df["Start"] + 1
    if "Strand" not in df.columns:
        df["Strand"] = "+"
    return df[["Frame", "Start", "End", "Length (bp)", "Strand"]].reset_index(drop=True)


def _count_orfs(seq: str, min_len: int = 30) -> int:
    """Return the number of ORFs detected by the shared sequence service."""
    return len(_get_orf_results(seq, min_len=min_len))


def _get_reverse_complement(seq: str) -> str:
    from services.sequence_service import reverse_complement

    return reverse_complement(seq)


def _get_translation_preview(seq: str, max_aa: int = 1000) -> tuple[str, bool]:
    """Return a bounded protein translation preview and truncation status."""
    if not seq:
        return "", False
    from services.sequence_service import translate

    protein = translate(seq) or ""
    if len(protein) <= max_aa:
        return protein, False
    return protein[:max_aa], True


def _colorise_seq(seq: str, width: int = 60) -> str:
    colors = {"A": "#ef4444", "T": "#3b82f6", "C": "#22c55e", "G": "#f59e0b", "N": "#9ca3af"}
    lines = []
    for i in range(0, len(seq), width):
        chunk = seq[i:i + width]
        prefix = f"<span style='color:#94a3b8;font-size:.6rem;user-select:none'>{i + 1:6d} </span>"
        bases = "".join(f"<span style='color:{colors.get(base, '#374151')}'>{base}</span>" for base in chunk)
        lines.append(prefix + bases)
    return "<br>".join(lines)


def _restriction_text_map(seq: str) -> str:
    from components.test_modules.seq_utils import find_enzymes

    hits = find_enzymes(seq)
    if not hits:
        return _t("sequence_tools.no_restriction_sites")
    seq_len = len(seq)
    lines = []
    for hit in hits[:20]:
        pos = hit["Position"] - 1
        arrow_pct = int(pos / max(seq_len, 1) * 58)
        bar = "─" * arrow_pct + "▼" + "─" * (58 - arrow_pct)
        lines.append(f"{hit['Enzyme']:<12s} {bar}  @{hit['Position']} ({hit['Type'][0]})")
    if len(hits) > 20:
        lines.append(_t("sequence_tools.extra_sites", count=len(hits) - 20))
    return "\n".join(lines)


def _can_send_to_wizard(result: SequenceInspectionResult, seq: str) -> bool:
    """Return True only for sequences that satisfy the shared ready preflight status."""
    return bool(seq) and result.status == "Ready for Wizard"


def _verification_adapter_for_source(source: str):
    if source == SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE:
        return LocalRegistryVerificationAdapter(), SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE
    return None, "Placeholder verification adapter"


def _verification_signature_from_result(result: dict | None) -> str | None:
    if not isinstance(result, dict):
        return None
    query = result.get("query") if isinstance(result.get("query"), dict) else {}
    value = query.get("signature") or query.get("sequence_signature") or result.get("sequence_signature")
    return str(value) if value else None


def _verification_database_source(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    database = result.get("database") if isinstance(result.get("database"), dict) else {}
    return str(database.get("source") or "")


def _verification_no_hit_message(result: dict) -> str:
    source = _verification_database_source(result)
    if source == SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE:
        return SEQUENCE_TOOLS_BLAST_NO_HIT_MESSAGE
    if source == SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE:
        return SEQUENCE_TOOLS_LOCAL_NO_HIT_MESSAGE
    return SEQUENCE_TOOLS_PLACEHOLDER_NO_HIT_MESSAGE


def _is_verification_result_stale(result: dict | None, current_signature: str) -> bool:
    result_signature = _verification_signature_from_result(result)
    return bool(result_signature and current_signature and result_signature != current_signature)


def _render_composition_details(seq: str, analysis_has_run: bool) -> None:
    """Render base composition only after a formal analysis result exists."""
    if not analysis_has_run:
        st.caption(SEQUENCE_TOOLS_COMPOSITION_PENDING_MESSAGE)
        return

    total_len = max(len(seq), 1)
    st.markdown(
        f"| Base | Count | Fraction |\n|---|---:|---:|\n"
        f"| A | {seq.count('A')} | {seq.count('A') / total_len * 100:.1f}% |\n"
        f"| T | {seq.count('T')} | {seq.count('T') / total_len * 100:.1f}% |\n"
        f"| C | {seq.count('C')} | {seq.count('C') / total_len * 100:.1f}% |\n"
        f"| G | {seq.count('G')} | {seq.count('G') / total_len * 100:.1f}% |"
    )


def _render_verification_panel(seq: str, source_label: str = "Current Sequence Tools sequence") -> None:
    """Render read-only sequence verification evidence without design-state mutation."""
    import pandas as pd

    st.markdown("#### Sequence Verification")
    st.caption(
        "BLAST-style similarity evidence for the current analyzed sequence. "
        "This is separate from Step 5 validation and Step 6 export recommendation."
    )
    st.info(SEQUENCE_VERIFICATION_DISCLAIMER)

    source_options = [
        SEQUENCE_TOOLS_LOCAL_REGISTRY_SOURCE,
        SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE,
        SEQUENCE_TOOLS_PLACEHOLDER_SOURCE,
    ]
    selected_source = st.selectbox(
        "Verification source",
        source_options,
        index=0,
        key=SEQUENCE_TOOLS_VERIFICATION_SOURCE_KEY,
    )

    imported_blast_tsv = ""
    if selected_source == SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE:
        st.caption("Paste BLAST tabular output or upload a TSV file generated outside BioDesign Studio. No online lookup is performed.")
        imported_blast_tsv = st.text_area(
            "Imported BLAST TSV",
            height=160,
            key=SEQUENCE_TOOLS_IMPORTED_BLAST_INPUT_KEY,
            placeholder="qseqid\tsseqid\tpident\tlength\tmismatch\tgapopen\tqstart\tqend\tsstart\tsend\tevalue\tbitscore",
        )
        uploaded_blast_file = st.file_uploader(
            "Upload BLAST TSV file",
            type=["tsv", "txt"],
            key="seq_tools_imported_blast_file",
        )
        if uploaded_blast_file is not None:
            try:
                imported_blast_tsv = uploaded_blast_file.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                imported_blast_tsv = uploaded_blast_file.getvalue().decode("utf-8", errors="replace")

    current_signature = _sequence_signature(seq)

    if st.button("Run Verification", key="seq_tools_run_verification", use_container_width=True):
        if selected_source == SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE:
            imported_payload = build_blast_import_payload(imported_blast_tsv, query_length=len(seq))
            adapter = {"status": imported_payload.get("status"), "hits": imported_payload.get("hits", [])}
            database_label = SEQUENCE_TOOLS_IMPORTED_BLAST_SOURCE
        else:
            adapter, database_label = _verification_adapter_for_source(selected_source)
        verification_result = run_sequence_verification(
            seq,
            source_label=source_label,
            adapter=adapter,
            database_label=database_label,
        )
        verification_result.setdefault("query", {})["signature"] = current_signature
        st.session_state[SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY] = verification_result
        st.session_state[SEQUENCE_TOOLS_VERIFICATION_SIGNATURE_KEY] = current_signature

    result = st.session_state.get(SEQUENCE_TOOLS_VERIFICATION_RESULT_KEY)
    if _is_verification_result_stale(result, current_signature):
        st.warning(SEQUENCE_TOOLS_VERIFICATION_STALE_MESSAGE)
    if not isinstance(result, dict):
        st.info(SEQUENCE_TOOLS_VERIFICATION_EMPTY_MESSAGE)
        return

    query = result.get("query") if isinstance(result.get("query"), dict) else {}
    database = result.get("database") if isinstance(result.get("database"), dict) else {}
    st.markdown("##### Verification summary")
    st.caption(SEQUENCE_TOOLS_VERIFICATION_SUMMARY_COPY)
    metric_cols = st.columns(3)
    metric_cols[0].metric("Query length", f"{int(query.get('length') or 0):,} bp")
    metric_cols[1].metric("Status", str(result.get("status") or "not_run"))
    metric_cols[2].metric("Database/source", str(database.get("source") or "Not configured"))
    st.caption(f"Timestamp: {result.get('timestamp') or 'Not available'}")
    st.caption(f"Adapter name: {result.get('adapter_name') or 'Not configured'}")

    top_hit = result.get("top_hit") if isinstance(result.get("top_hit"), dict) else None
    if top_hit:
        st.markdown("##### Top hit summary")
        st.write(
            f"{top_hit.get('accession') or 'No accession'} · "
            f"{top_hit.get('organism') or 'Unknown host'} · "
            f"{top_hit.get('match_type') or 'similarity hit'} · "
            f"{top_hit.get('percent_identity') if top_hit.get('percent_identity') is not None else 'NA'}% identity · "
            f"{top_hit.get('coverage') if top_hit.get('coverage') is not None else 'NA'}% coverage"
        )
        if top_hit.get("alignment_summary"):
            st.caption(str(top_hit["alignment_summary"]))
    else:
        status = str(result.get("status") or "not_run")
        if status == "no_hits":
            st.info(_verification_no_hit_message(result))
        elif status == "unavailable":
            st.warning(SEQUENCE_TOOLS_UNAVAILABLE_MESSAGE)
        else:
            st.info("No top similarity hit is available from the current verification adapter.")

    hits = result.get("hits") if isinstance(result.get("hits"), list) else []
    if hits:
        st.markdown("##### Top hits table")
        rows = [
            {
                "Rank": hit.get("rank"),
                "Accession": hit.get("accession"),
                "Host": hit.get("organism"),
                "Description": hit.get("description"),
                "Identity %": hit.get("percent_identity"),
                "Coverage %": hit.get("coverage"),
                "E-value": hit.get("e_value"),
                "Bitscore": hit.get("bitscore"),
                "Alignment length": hit.get("alignment_length"),
                "Match type": hit.get("match_type"),
                "Part type": hit.get("part_type"),
                "Source": hit.get("source"),
                "Alignment summary": hit.get("alignment_summary"),
            }
            for hit in hits
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    if warnings:
        st.markdown("##### Warnings")
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            code = warning.get("code") or "INFORMATIONAL_ONLY"
            message = warning.get("message") or "Review this verification signal manually."
            severity = warning.get("severity") or "info"
            text = f"{code}: {message}"
            if severity == "warning":
                st.warning(text)
            else:
                st.info(text)

    st.caption(f"Disclaimer: {result.get('disclaimer') or SEQUENCE_VERIFICATION_DISCLAIMER}")


def _render_preflight_panel(
    result: SequenceInspectionResult,
    seq: str,
    change_page=None,
    can_send: bool | None = None,
    is_stale: bool = False,
) -> None:
    status_tone = {
        "Ready for Wizard": "success",
        "Needs Review": "warning",
        "Invalid Sequence": "error",
    }.get(result.status, "info")

    st.markdown("#### Sequence review notes")
    if is_stale:
        st.warning(SEQUENCE_TOOLS_STALE_MESSAGE)
    status_message = f"Previous review note: {result.status}" if is_stale else f"Review note: {result.status}"
    if status_tone == "success":
        st.info(status_message)
    elif status_tone == "warning":
        st.warning(status_message)
    else:
        st.error(status_message)

    metrics = st.columns(4)
    metrics[0].metric("Sequence length", f"{result.length:,} bp")
    metrics[1].metric("Valid bases", "Yes" if result.valid_bases else "No")
    metrics[2].metric("GC percentage", f"{result.gc_percentage:.1f}%")
    metrics[3].metric("Protein length", str(result.translated_protein_length) if result.translated_protein_length is not None else "Review")

    cds_checks = [
        ("Length divisible by 3", result.length_divisible_by_3),
        ("Starts with ATG", result.starts_with_atg),
        ("Ends with stop codon", result.ends_with_stop_codon),
        ("Internal stop codon", not result.has_internal_stop_codon),
    ]
    for label, passed in cds_checks:
        st.write(f"{'No flagged issue' if passed else 'Flagged for review'} - {label}")

    if result.invalid_characters:
        invalid_text = ", ".join(f"{item.character} ({item.count})" for item in result.invalid_characters)
        st.error(f"Invalid characters: {invalid_text}")
    else:
        st.caption("Invalid characters: none")

    for error in result.errors:
        st.error(error)
    for warning in result.warnings:
        st.warning(warning)

    send_enabled = _can_send_to_wizard(result, seq) if can_send is None else can_send
    if st.button(
        "Use in Wizard",
        key="st_preflight_use_in_wizard",
        type="primary" if result.status == "Ready for Wizard" else "secondary",
        use_container_width=True,
        disabled=not send_enabled,
        help=(
            SEQUENCE_TOOLS_HANDOFF_CONTEXT_COPY
            if send_enabled
            else SEQUENCE_TOOLS_DISABLED_SEND_HELPER
        ),
    ):
        from core.context_bridge import send_seq_to_wizard

        send_seq_to_wizard(seq, change_page=change_page)

    if is_stale:
        st.caption(SEQUENCE_TOOLS_STALE_MESSAGE)
    elif result.status != "Ready for Wizard" and bool(seq) and result.status != "Invalid Sequence":
        st.caption(SEQUENCE_TOOLS_NEEDS_REVIEW_MESSAGE)


def render(change_page=None) -> None:  # noqa: ARG001
    st.markdown(_CSS, unsafe_allow_html=True)
    inject_tool_typography_css()
    current_seq = st.session_state.get(SK.ACTIVE_SEQ, "")
    if current_seq and "seq_tools_source" not in st.session_state:
        st.session_state["seq_tools_source"] = "external"
    ready = st.session_state.get("seq_tools_ready", bool(current_seq))
    source = st.session_state.get("seq_tools_source")
    seq = current_seq if ready and current_seq else ""

    st.markdown(
        f"<div class='page-hero'><div class='kicker'>{_t('sequence_tools.title')}</div>"
        f"<div style='font-size:1.65rem;font-weight:800;color:#0f172a;margin:.2rem 0'>{_t('sequence_tools.hero_title')}</div>"
        f"<div style='font-size:.92rem;color:#475569'>{_t('sequence_tools.hero_body')}</div></div>",
        unsafe_allow_html=True,
    )

    render_boundary_note(_t("sequence_tools.standalone_notice"))
    render_tool_intro(
        "Documentation inspection helper",
        "Input: pasted DNA or a loaded example. Output: local sequence inspection summary, sequence metrics, "
        "ORF/restriction/composition previews, documentation notes, and documentation-only review notes. "
        "Next step: paste a sequence and select Generate Preview; use in Wizard remains unavailable until the current input has been analyzed without review-blocking notes. "
        "This helper is not validation, not prediction, not recommendation, not readiness approval, and not a wet-lab protocol.",
    )

    st.markdown("<div class='input-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='kicker'>{_t('sequence_tools.step1')}</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:1.05rem;font-weight:700;color:#0f172a;margin:.15rem 0 .35rem 0'>{_t('sequence_tools.input_title')}</div>", unsafe_allow_html=True)
    helper = _t("sequence_tools.helper.initial")
    if ready and source == "example":
        helper = _t("sequence_tools.helper.example")
    elif ready:
        helper = _t("sequence_tools.helper.ready")
    st.caption(helper)

    pasted = st.text_area(_t("sequence_tools.input_label"), placeholder=_t("sequence_tools.input_placeholder"), height=180, key="seq_tools_paste_input")
    current_input_signature = _sequence_signature(pasted)
    analyzed_signature = st.session_state.get(SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY)
    analysis_stale = _is_analysis_stale(current_input_signature, analyzed_signature)
    c1, c2, c3 = st.columns([1.15, 1, 1.2])
    run_btn = c1.button(_t("sequence_tools.run"), type="primary", use_container_width=True, key="st_run")
    demo_btn = c2.button(_t("sequence_tools.demo"), use_container_width=True, key="st_demo")
    send_result = inspect_sequence(st.session_state.get(SEQUENCE_TOOLS_RAW_INPUT_KEY, seq)) if ready and seq else None
    send_ready = _can_use_analyzed_result(send_result, current_input_signature, analyzed_signature)
    if analysis_stale:
        c3.warning(SEQUENCE_TOOLS_STALE_MESSAGE)
    if c3.button(
        _t("sequence_tools.send_to_wizard"),
        key="st_send_to_wizard",
        use_container_width=True,
        help=SEQUENCE_TOOLS_HANDOFF_CONTEXT_COPY if send_ready else SEQUENCE_TOOLS_DISABLED_SEND_HELPER,
        disabled=not send_ready,
    ):
        from core.context_bridge import send_seq_to_wizard
        send_seq_to_wizard(seq, change_page=change_page)
    if ready and seq and not send_ready and not analysis_stale:
        c3.caption(SEQUENCE_TOOLS_DISABLED_SEND_HELPER)
    elif ready and seq and send_ready:
        c3.caption(SEQUENCE_TOOLS_HANDOFF_CONTEXT_COPY)

    if demo_btn:
        st.session_state[SK.ACTIVE_SEQ] = _DEFAULT_SEQ
        st.session_state[SEQUENCE_TOOLS_RAW_INPUT_KEY] = _DEFAULT_SEQ
        st.session_state[SEQUENCE_TOOLS_ANALYZED_TEXT_KEY] = _DEFAULT_SEQ
        st.session_state[SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY] = _sequence_signature(_DEFAULT_SEQ)
        st.session_state["seq_tools_ready"] = True
        st.session_state["seq_tools_source"] = "example"
        st.session_state.pop(SEQUENCE_TOOLS_ERROR_KEY, None)
        st.rerun()
    if run_btn:
        raw_result = inspect_sequence(pasted)
        cleaned, err = _clean_input(pasted)
        if raw_result.status == "Invalid Sequence":
            st.session_state[SK.ACTIVE_SEQ] = raw_result.sequence
            st.session_state[SEQUENCE_TOOLS_RAW_INPUT_KEY] = pasted
            st.session_state[SEQUENCE_TOOLS_ANALYZED_TEXT_KEY] = pasted
            st.session_state[SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY] = raw_result.sequence
            st.session_state["seq_tools_ready"] = True
            st.session_state["seq_tools_source"] = "invalid"
            st.session_state[SEQUENCE_TOOLS_ERROR_KEY] = err or "Invalid sequence input."
            st.rerun()
        elif err:
            st.session_state["seq_tools_ready"] = False
            st.session_state[SEQUENCE_TOOLS_ANALYZED_TEXT_KEY] = pasted
            st.session_state[SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY] = current_input_signature
            st.session_state["seq_tools_source"] = "invalid"
            st.session_state[SEQUENCE_TOOLS_ERROR_KEY] = err
            st.rerun()
        else:
            st.session_state[SK.ACTIVE_SEQ] = cleaned
            st.session_state[SEQUENCE_TOOLS_RAW_INPUT_KEY] = pasted
            st.session_state[SEQUENCE_TOOLS_ANALYZED_TEXT_KEY] = pasted
            st.session_state[SEQUENCE_TOOLS_ANALYZED_SIGNATURE_KEY] = cleaned
            st.session_state["seq_tools_ready"] = True
            st.session_state["seq_tools_source"] = "input"
            st.session_state.pop(SEQUENCE_TOOLS_ERROR_KEY, None)
            st.success(_t("sequence_tools.loaded_success", length=len(cleaned)))
            st.rerun()

    validation_error = st.session_state.get(SEQUENCE_TOOLS_ERROR_KEY)
    has_displayed_result = bool(st.session_state.get("seq_tools_ready") and st.session_state.get(SK.ACTIVE_SEQ, ""))
    if validation_error and not has_displayed_result:
        st.error(validation_error)
    elif has_displayed_result:
        st.session_state.pop(SEQUENCE_TOOLS_ERROR_KEY, None)

    o1, o2 = st.columns(2)
    with o1:
        with st.expander(_t("sequence_tools.view_options"), expanded=False):
            st.checkbox(_t("sequence_tools.show_rc"), value=False, key="st_show_rc")
            st.checkbox(_t("sequence_tools.show_translation"), value=False, key="st_show_trans")
    with o2:
        with st.expander(_t("sequence_tools.composition_details"), expanded=False):
            _render_composition_details(seq, analysis_has_run=bool(ready and seq))
    st.markdown("</div>", unsafe_allow_html=True)

    if not ready or not seq:
        st.markdown(f"<div class='placeholder-card'><div class='kicker'>{_t('sequence_tools.step2')}</div><div style='font-size:1.1rem;font-weight:700;color:#0f172a;margin:.3rem 0'>{_t('sequence_tools.result_pending_title')}</div><div style='font-size:.88rem'>{_t('sequence_tools.result_pending_body')}</div></div>", unsafe_allow_html=True)
        return

    if source == "example":
        st.markdown(f"<div class='inline-note'>{_t('sequence_tools.example_note')}</div>", unsafe_allow_html=True)

    gc = round(compute_gc(seq), 1)
    preflight_result = inspect_sequence(st.session_state.get(SEQUENCE_TOOLS_RAW_INPUT_KEY, seq))
    mw = _calc_mw(seq)
    orf_min_len = st.slider(_t("sequence_tools.orf_min_len"), min_value=30, max_value=900, value=30, step=3, key="st_orf_min_len")
    st.caption(_t("sequence_tools.orf_scope_note"))
    st.caption(SEQUENCE_TOOLS_DOCUMENTATION_CONTEXT_COPY)
    orf_df = _get_orf_results(seq, min_len=orf_min_len)

    m = st.columns(5)
    m[0].metric(_t("sequence_tools.metric.length"), f"{len(seq):,} bp")
    m[1].metric(_t("sequence_tools.metric.gc"), f"{gc} %")
    m[2].metric(_t("sequence_tools.metric.mw"), f"{mw / 1000:.1f} kDa")
    m[3].metric(_t("sequence_tools.metric.orf"), f"{len(orf_df)}")
    m[4].metric(_t("sequence_tools.metric.base_counts"), f"{seq.count('A')}/{seq.count('T')}/{seq.count('C')}/{seq.count('G')}")

    col_seq, col_side = st.columns([1.65, 1], gap="large")
    with col_seq:
        st.markdown(f"<div class='result-card'><div class='kicker'>{_t('sequence_tools.main_result')}</div><div style='font-size:1rem;font-weight:700;color:#0f172a;margin:.15rem 0 .5rem 0'>{_t('sequence_tools.viewer_title')}</div>", unsafe_allow_html=True)
        display_seq = seq[:6000]
        suffix = f"<br><span style='color:#94a3b8;font-size:.6rem'>{_t('sequence_tools.viewer_prefix_only', length=len(seq))}</span>" if len(seq) > 6000 else ""
        st.markdown("<div class='seq-block'>" + _colorise_seq(display_seq) + suffix + "</div>", unsafe_allow_html=True)
        if st.session_state.get("st_show_rc", False):
            st.markdown(f"<div style='font-size:.76rem;font-weight:700;color:#475569;margin-top:10px'>{_t('sequence_tools.reverse_complement')}</div>", unsafe_allow_html=True)
            st.code(_get_reverse_complement(seq)[:3000], language=None)
        if st.session_state.get("st_show_trans", False):
            protein, truncated = _get_translation_preview(seq)
            st.markdown(f"<div style='font-size:.76rem;font-weight:700;color:#475569;margin-top:10px'>{_t('sequence_tools.translation_title')}</div>", unsafe_allow_html=True)
            st.caption(_t("sequence_tools.translation_scope_note"))
            if protein:
                st.code(protein, language=None)
                if truncated:
                    st.caption(_t("sequence_tools.translation_truncated"))
            else:
                st.caption(_t("sequence_tools.translation_unavailable"))
        if orf_df.empty:
            st.caption(_t("sequence_tools.no_orf"))
        else:
            st.dataframe(orf_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_side:
        st.markdown(f"<div class='result-card'><div class='kicker'>{_t('sequence_tools.side_analysis')}</div>", unsafe_allow_html=True)
        tabs = st.tabs(["Preflight", "Verification", _t("sequence_tools.restriction_map"), _t("sequence_tools.base_composition"), _t("sequence_tools.more_tools")])
        with tabs[0]:
            _render_preflight_panel(
                preflight_result,
                seq,
                change_page=change_page,
                can_send=send_ready,
                is_stale=analysis_stale,
            )
        with tabs[1]:
            _render_verification_panel(seq)
        with tabs[2]:
            st.markdown(f"<div style='font-size:.95rem;font-weight:700;color:#0f172a;margin:.1rem 0 .5rem 0'>{_t('sequence_tools.restriction_overview')}</div>", unsafe_allow_html=True)
            st.caption(_t("sequence_tools.restriction_scope_note"))
            st.code(_restriction_text_map(seq), language=None)
        with tabs[3]:
            import pandas as pd
            st.markdown(f"<div style='font-size:.95rem;font-weight:700;color:#0f172a;margin:.1rem 0 .5rem 0'>{_t('sequence_tools.base_composition')}</div>", unsafe_allow_html=True)
            st.bar_chart(pd.DataFrame({"Count": {"A": seq.count("A"), "T": seq.count("T"), "C": seq.count("C"), "G": seq.count("G")}}), use_container_width=True)
        with tabs[4]:
            st.markdown(f"##### {_t('sequence_tools.more_tools_title')}")
