# -*- coding: utf-8 -*-
"""
views/wizard_steps/step1_gene_input.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step 1 -- Gene Input.
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Tuple

import streamlit as st

from core.session_keys import SK
from services.sequence_inspector import (
    SequenceInspectionResult,
    WIZARD_MINIMUM_SEQUENCE_LENGTH,
    PreflightStatus,
    inspect_sequence,
)
from services.wizard_state_service import hydrate_wizard_widgets_from_design_session
from views.wizard_steps._shared import (
    _clean_seq,
    _check_dna_input,
    _validate_cds_sequence,
    _gc,
    _section_label,
    _status_panel,
    _step_header,
    render_flow_strip,
)


def _clean_pasted_gene_input(raw: str, use_service_cleaner: bool) -> Tuple[str, List[str]]:
    """Backward-compatible wrapper for tests and existing callers."""
    if not raw:
        return "", []

    sequence_lines = [ln for ln in raw.splitlines() if not ln.strip().startswith(">")]
    sequence_text = "\n".join(sequence_lines)

    if use_service_cleaner:
        from services.sequence_service import clean as _svc_clean

        return _svc_clean(sequence_text)

    return _clean_seq(sequence_text), []


def _build_sequence_feedback(raw: str, cleaned: str) -> Dict[str, Any]:
    """Summarize how raw sequence text was interpreted and cleaned."""
    text = str(raw or "")
    if not text.strip():
        return {
            "cleaned": cleaned,
            "headers": 0,
            "line_count": 0,
            "raw_length": 0,
            "kept_bases": len(cleaned),
            "invalid_count": 0,
            "invalid_examples": [],
            "notes": [],
        }

    lines = text.splitlines()
    sequence_lines = [ln for ln in lines if not ln.strip().startswith(">")]
    joined_sequence_text = "".join(sequence_lines)
    alpha_chars = [char.upper() for char in joined_sequence_text if char.isalpha()]
    invalid_chars = [char for char in alpha_chars if char not in {"A", "T", "C", "G", "N"}]

    return {
        "cleaned": cleaned,
        "headers": sum(1 for ln in lines if ln.strip().startswith(">")),
        "line_count": len(lines),
        "raw_length": len(text.strip()),
        "kept_bases": len(cleaned),
        "invalid_count": len(invalid_chars),
        "invalid_examples": sorted(set(invalid_chars))[:6],
        "notes": [],
    }


def _resolve_step1_readiness(preflight_input: str | None) -> tuple[Any | None, PreflightStatus | None, bool]:
    """Resolve the single Step 1 readiness status from Sequence Inspector."""
    if not preflight_input or not str(preflight_input).strip():
        return None, None, False

    result = inspect_sequence(preflight_input)
    status = result.status
    return result, status, status == "Ready for Wizard"


def _build_step1_preflight_detail_message(result: SequenceInspectionResult) -> str:
    """Return MVP-specific Step 1 wording without changing preflight semantics."""
    if result.status == "Invalid Sequence":
        return (
            "Invalid Sequence: The input sequence cannot be used as provided. "
            "Please correct the sequence and run preflight again."
        )

    if result.status == "Needs Review":
        if result.length < WIZARD_MINIMUM_SEQUENCE_LENGTH:
            return (
                "Too Short: The sequence is shorter than the current MVP expects for wizard entry. "
                "Please review the input and provide a complete coding sequence."
            )
        return (
            "Needs Review: Review-blocking preflight signals remain. In the current MVP, "
            "Step 1 can only be confirmed when the sequence status is Ready for Wizard."
        )

    return (
        "Ready for Wizard: The sequence can proceed to Step 1 confirmation. "
        "This does not mean the design has passed downstream validation or supports experimental use."
    )


def _render_preflight_summary(
    seq: str,
    raw_input: str | None = None,
    readiness_result: Any | None = None,
    readiness_status: PreflightStatus | None = None,
) -> None:
    """Render a lightweight Sequence Inspector summary for Step 1."""
    inspection_input = raw_input if raw_input and raw_input.strip() else seq
    if not inspection_input:
        return

    if readiness_result is None or readiness_status is None:
        readiness_result, readiness_status, _ = _resolve_step1_readiness(inspection_input)
    if readiness_result is None or readiness_status is None:
        return

    result = readiness_result
    display_status = readiness_status
    tone = "ready" if display_status == "Ready for Wizard" else "warn"
    _status_panel(
        "Preflight summary",
        "Preflight checks help determine whether the sequence can enter the Expression Wizard. "
        "Preflight does not replace downstream validation and does not indicate experimental readiness. "
        f"Sequence Inspector status: {display_status}. GC: {result.gc_percentage:.1f}%. "
        f"Protein length: {result.translated_protein_length if result.translated_protein_length is not None else 'requires review'}. "
        f"{_build_step1_preflight_detail_message(result)}",
        tone=tone,
    )
    if raw_input and raw_input.strip() and raw_input != seq:
        st.caption(f"Parsed sequence readiness: {len(seq)} retained base(s) for downstream wizard processing.")
    if result.invalid_characters:
        invalid_text = ", ".join(f"{item.character} ({item.count})" for item in result.invalid_characters)
        st.error(f"Raw input issues: invalid character(s): {invalid_text}")
    for error in result.errors:
        st.error(error)
    for warning in result.warnings[:4]:
        st.warning(warning)


def page(ctrl) -> None:
    """Render Step 1 -- Gene Input."""
    ds = ctrl.get()

    _sync_signature = (ds.gene_name or "", ds.original_seq or "")
    if st.session_state.get("_wf_p1_loaded_sync") != _sync_signature:
        hydrate_wizard_widgets_from_design_session(st.session_state, ds)

    _step_header(
        1,
        "Gene Input",
        "Import the target CDS for this design and record the target product/protein plus gene/CDS provenance for plant expression construct review.",
        [
            "Paste a sequence, upload a file, or import from the part registry.",
            "Preview length, GC content, and start/stop codon checks in real time.",
            "Plant MVP context: target product/protein and gene/CDS source provenance.",
            "Primary action: confirm the gene input.",
        ],
    )

    try:
        from services.sequence_service import clean as _svc_clean
        _SVC_OK = True
    except ImportError:
        _SVC_OK = False

    mode = st.radio(
        "Input mode",
        ["Paste sequence", "Upload file", "Import from registry"],
        horizontal=True, key="wf_p1_mode",
    )

    paste_feedback: Dict[str, Any] = {
        "cleaned": "",
        "headers": 0,
        "line_count": 0,
        "raw_length": 0,
        "kept_bases": 0,
        "invalid_count": 0,
        "invalid_examples": [],
        "notes": [],
    }

    col_left, col_right = st.columns([1.2, 1], gap="large")
    parsed_seq  = ""
    parsed_name = ds.gene_name or "Gene"

    with col_left:
        _section_label("Input panel")
        st.caption("Choose an input source and confirm the target gene sequence for this design.")
        if mode == "Paste sequence":
            parsed_name = st.text_input(
                "Gene name", value=ds.gene_name or "",
                placeholder="For example: OsWRKY45", key="wf_p1_name"
            )
            raw = st.text_area(
                "Paste FASTA or plain DNA sequence", value=ds.original_seq or "",
                height=170, placeholder=">MyGene\nATGGCTAGC...", key="wf_p1_seq"
            )
            paste_feedback = _build_sequence_feedback(raw, "")
            if _SVC_OK:
                cleaned, warns = _clean_pasted_gene_input(raw, use_service_cleaner=True)
                parsed_seq = cleaned
                paste_feedback = _build_sequence_feedback(raw, cleaned)
                paste_feedback["notes"] = list(warns)
                for w in warns:
                    st.warning(f"Sequence warning: {w}")
            else:
                parsed_seq, _ = _clean_pasted_gene_input(raw, use_service_cleaner=False)
                paste_feedback = _build_sequence_feedback(raw, parsed_seq)

            if raw.strip():
                info_cols = st.columns(4)
                info_cols[0].metric("Input lines", paste_feedback["line_count"])
                info_cols[1].metric("FASTA headers", paste_feedback["headers"])
                info_cols[2].metric("Retained bases", paste_feedback["kept_bases"])
                info_cols[3].metric("Removed letters", paste_feedback["invalid_count"])

                removed_non_base_chars = [
                    char
                    for char in raw
                    if char not in {"A", "T", "C", "G", "N", "a", "t", "c", "g", "n"}
                    and not char.isspace()
                    and char not in {">", "-", ".", "…", "⋯"}
                ]

                if removed_non_base_chars:
                    invalid_examples = ", ".join(paste_feedback["invalid_examples"]) or "non-DNA letters"
                    st.warning(
                        f"Removed {paste_feedback['invalid_count']} non-DNA character(s) from the input. "
                        f"Examples: {invalid_examples}. Only A, T, C, G, and N are retained in the cleaned DNA sequence."
                    )
                elif parsed_seq and any(char in raw for char in (" ", "\n", "\r", "\t", "-", ".", "…", "⋯")):
                    st.info("Whitespace or formatting characters were ignored during parsing.")

                if paste_feedback["headers"] > 1:
                    st.info(
                        "Multiple FASTA headers were detected. All header lines were ignored and the remaining DNA lines were merged into one sequence."
                    )

                if raw.lstrip().startswith(">") and not parsed_seq:
                    st.error(
                        "A FASTA header was detected, but no DNA sequence lines were found under it. Paste the nucleotide lines after the header."
                    )

        elif mode == "Upload file":
            up = st.file_uploader(
                "Upload .fasta / .fa / .txt / .gb",
                type=["fasta", "fa", "txt", "gb", "gbk"], key="wf_p1_upload"
            )
            if up is not None:
                raw_bytes = up.read()
                try:
                    raw_text = raw_bytes.decode("utf-8")
                except Exception:
                    raw_text = raw_bytes.decode("latin-1")
                with st.spinner(f"Reading {up.name}..."):
                    if up.name.endswith((".gb", ".gbk")):
                        try:
                            from Bio import SeqIO as _SI
                            rec = next(_SI.parse(io.StringIO(raw_text), "genbank"), None)
                            if rec:
                                parsed_seq = str(rec.seq).upper()
                                parsed_name = rec.name
                                st.success(f"GenBank loaded: {rec.description[:60]} ({len(parsed_seq)} bp)")
                            else:
                                st.error("No valid GenBank record was found.")
                        except ImportError:
                            st.error("Biopython is required to parse GenBank files.")
                        except Exception as e:
                            st.error(f"GenBank parsing error: {e}")
                    else:
                        upload_feedback = _build_sequence_feedback(raw_text, "")
                        if _SVC_OK:
                            parsed_seq, warns = _svc_clean(raw_text)
                            upload_feedback = _build_sequence_feedback(raw_text, parsed_seq)
                            upload_feedback["notes"] = list(warns)
                            for w in warns:
                                st.warning(f"Sequence warning: {w}")
                        else:
                            parsed_seq = _clean_seq(raw_text)
                            upload_feedback = _build_sequence_feedback(raw_text, parsed_seq)
                        parsed_name = up.name.rsplit(".", 1)[0]
                        if parsed_seq:
                            st.success(f"Loaded {up.name} ({len(parsed_seq)} bp)")
                            st.caption(
                                f"Parsed {upload_feedback['kept_bases']} DNA bases from {upload_feedback['line_count']} line(s). "
                                f"Ignored {upload_feedback['headers']} FASTA header line(s)."
                            )
                            if upload_feedback["invalid_count"] > 0:
                                invalid_examples = ", ".join(upload_feedback["invalid_examples"]) or "non-DNA letters"
                                st.info(
                                    f"Removed {upload_feedback['invalid_count']} unsupported letter(s) while cleaning the file. "
                                    f"Examples: {invalid_examples}."
                                )
                        else:
                            st.error("No valid DNA sequence was found in the file.")
            else:
                st.info("Upload a FASTA or GenBank file to continue.")
            parsed_name = st.text_input("Gene name", value=parsed_name, key="wf_p1_name")

        else:  # Import from registry
            try:
                from services.parts_service import query_registry_parts
                parts = query_registry_parts(part_types=["CDS"])
                if not parts:
                    st.warning("No CDS parts were found in the registry.")
                else:
                    kw   = st.text_input("Search", placeholder="Filter by name...", key="wf_p1_search")
                    filt = [
                        part for part in parts
                        if not kw or kw.lower() in str(part.get("name", "")).lower()
                    ]
                    if filt:
                        part_names = [str(part.get("name", "")) for part in filt]
                        sel     = st.selectbox("Select a part", part_names, key="wf_p1_part")
                        row     = next((part for part in filt if part.get("name") == sel), {})
                        raw_p   = str(row.get("sequence") or "")
                        parsed_seq  = re.sub(r"[^ATCGNatcgn]", "", raw_p).upper()
                        parsed_name = sel
                        if parsed_seq:
                            st.success(f"Selected: {sel} ({len(parsed_seq)} bp)")
                        else:
                            st.warning("Only a sequence preview is available for this part.")
                    else:
                        st.info("No matching parts were found.")
            except Exception as e:
                st.error(f"Registry error: {e}")
            parsed_name = st.text_input("Gene name", value=parsed_name, key="wf_p1_name")

        # Local section readiness follows one Sequence Inspector-derived status.
        preflight_input = None
        if mode == "Paste sequence" and raw.strip():
            preflight_input = raw
        elif parsed_seq:
            preflight_input = parsed_seq
        preflight_result, preflight_status, step1_ready = _resolve_step1_readiness(preflight_input)
        if mode == "Paste sequence" and raw and raw.lstrip().startswith(">"):
            detected_format = "FASTA"
        elif mode == "Upload file" and parsed_seq and str(st.session_state.get("wf_p1_upload") or "").lower().endswith((".gb", ".gbk")):
            detected_format = "GenBank"
        elif mode == "Import from registry":
            detected_format = "Registry sequence"
        else:
            detected_format = "DNA text"

        if parsed_seq:
            preview_cols = st.columns(4)
            preview_cols[0].metric("Parsed format", detected_format)
            preview_cols[1].metric("Gene name", parsed_name or "Gene")
            preview_cols[2].metric("Length", f"{len(parsed_seq)} bp")
            preview_cols[3].metric("GC", f"{_gc(parsed_seq):.1f}%")
            render_flow_strip(
                [
                    ("Input", "Sequence source, name, and parsing status"),
                    ("Output", "Cleaned sequence preview, metrics, and preflight summary"),
                ]
            )
            preflight_raw = raw if mode == "Paste sequence" else None
            _render_preflight_summary(
                parsed_seq,
                raw_input=preflight_raw,
                readiness_result=preflight_result,
                readiness_status=preflight_status,
            )

        if step1_ready:
            _status_panel(
                "Ready for the next step",
                f"The current sequence meets the minimum requirement for downstream host and regulatory-element selection ({len(parsed_seq):,} bp).",
                tone="ready",
            )
        else:
            if preflight_status == "Invalid Sequence":
                blocked_message = "Step 1 cannot be confirmed while invalid sequence characters remain."
            elif parsed_seq and len(parsed_seq) >= WIZARD_MINIMUM_SEQUENCE_LENGTH:
                blocked_message = "Step 1 cannot be confirmed while review-blocking preflight signals remain."
            else:
                blocked_message = "Too Short: The sequence is shorter than the current MVP expects for wizard entry. Please review the input and provide a complete coding sequence."
            _status_panel(
                "A valid sequence is still required",
                blocked_message,
                tone="warn",
            )

        action_col_confirm, action_col_clear = st.columns([3, 1])
        with action_col_confirm:
            confirm_clicked = st.button(
                "Confirm gene input",
                type="primary",
                key="wf_p1_next",
                use_container_width=True,
                disabled=not step1_ready,
                help="Provide a valid DNA sequence of at least 30 bp before continuing." if not step1_ready else "",
            )
        with action_col_clear:
            if st.button("Clear", key="wf_p1_clear", use_container_width=True):
                st.session_state["wf_p1_name"] = ""
                st.session_state["wf_p1_seq"] = ""
                st.rerun()

        if confirm_clicked:
            if not parsed_seq:
                st.error("Provide a valid DNA sequence before continuing.")
            elif not step1_ready:
                st.error("Only sequences marked Ready for Wizard can be confirmed.")
            else:
                # DNA quality gate 1: protein/purity check on raw paste text
                _raw = st.session_state.get("wf_p1_seq", "") if mode == "Paste sequence" else ""
                _ok, _err = _check_dna_input(_raw) if _raw else (True, "")
                # DNA quality gate 2: strict CDS checks on cleaned sequence
                _validation_errors = _validate_cds_sequence(parsed_seq)

                if not _ok:
                    st.error(_err)
                elif len(set(parsed_seq)) < 2:
                    st.error(
                        "Sequence lacks nucleotide diversity (only one base detected). "
                        "Please verify the input sequence."
                    )
                elif _validation_errors:
                    for err in _validation_errors:
                        st.error(err)
                else:
                    committed_name = parsed_name or "Gene"
                    identity_changed = (
                        ds.original_seq != parsed_seq
                        or ds.gene_name != committed_name
                    )
                    # Invalidate downstream data when gene identity changes.
                    # This logic belongs here because only the UI knows when
                    # the user has committed a new sequence.
                    if identity_changed:
                        ds.optimized_seq = ""
                        ds.frame = {}
                        ds.primers = []
                        ds.validation_results = []
                        for key in (
                            "wf_p4_primers_ctx_host",
                            "wf_p4_primers_ctx_seq_hash",
                            "wf_plasmid_png",
                            "wf_plasmid_features",
                            "wf_plasmid_title",
                        ):
                            st.session_state.pop(key, None)

                    ds.original_seq = parsed_seq
                    ds.gene_name = committed_name
                    st.session_state[SK.ACTIVE_SEQ] = parsed_seq
                    ctrl.save(ds)
                    ctrl.advance()

    # ── Right column: live sequence preview ──────────────────────────────────
    with col_right:
        _section_label("Live preview")
        st.caption("Review sequence quality and CDS structure before confirmation.")
        # resolve preview from state or live input
        preview = parsed_seq or (
            _clean_pasted_gene_input(st.session_state.get("wf_p1_seq", ""), use_service_cleaner=False)[0]
            if mode == "Paste sequence" else ""
        )
        if preview:
            gc_val   = _gc(preview)
            has_atg  = preview.startswith("ATG")
            has_stop = len(preview) >= 3 and preview[-3:] in ("TAA", "TAG", "TGA")
            c_atg    = "#16a34a" if has_atg  else "#dc2626"
            c_stop   = "#16a34a" if has_stop else "#dc2626"
            t_atg    = "ATG present" if has_atg  else "Missing"
            t_stop   = "Valid stop"  if has_stop else "Missing"
            st.markdown(
                f'<div class="mstrip">'
                f'<div class="mchip"><div class="mchip-label">Length</div>'
                f'<div class="mchip-value">{len(preview)} bp</div></div>'
                f'<div class="mchip"><div class="mchip-label">GC</div>'
                f'<div class="mchip-value">{gc_val:.1f}%</div></div>'
                f'<div class="mchip"><div class="mchip-label">Start codon</div>'
                f'<div class="mchip-value" style="color:{c_atg}">{t_atg}</div></div>'
                f'<div class="mchip"><div class="mchip-label">Stop codon</div>'
                f'<div class="mchip-value" style="color:{c_stop}">{t_stop}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            # Inline warnings -- no full-width banners
            if not has_atg:
                st.warning("Start codon check failed: sequence does not start with ATG.", icon="⚠️")
            if not has_stop:
                st.warning("Stop codon check failed: sequence does not end with TAA, TAG, or TGA.", icon="⚠️")
            # st.code gives syntax highlighting + one-click copy button
            display_seq = preview[:300] + ("..." if len(preview) > 300 else "")
            st.code(display_seq, language="text")
        else:
            _status_panel(
                "Waiting for sequence input",
                "After you provide a sequence, this panel shows the cleaned preview, key metrics, and basic CDS checks.",
                tone="info",
            )
