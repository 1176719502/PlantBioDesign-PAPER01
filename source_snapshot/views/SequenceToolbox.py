"""Formal read-only DNA sequence analysis page."""
from __future__ import annotations

import streamlit as st
from core.i18n import t as _t
from services.dna_sequence_analysis import (
    DNA_IUPAC_ANALYSIS_ALPHABET,
    RNA_IUPAC_ALPHABET,
    SequenceTransformError,
    SequenceTransformMode,
    normalize_sequence_text,
    transform_dna_rna,
)
from services.sequence_service import normalized_orfs, translate_frame

from services.dna_sequence_analysis import (
    DnaSequenceAnalysisResult,
    SequenceErrorCode,
    SequenceTopology,
    SequenceWarningCode,
    analyze_dna_sequence,
)


SEQUENCE_INPUT_KEY = "sequence_toolbox_raw_input"
TOPOLOGY_KEY = "sequence_toolbox_topology"
RESULT_KEY = "sequence_toolbox_result"
TRANSFORM_RESULT_KEY = "sequence_toolbox_transform_result"
TRANSLATION_RESULT_KEY = "sequence_toolbox_translation_result"
TRANSFORM_RESULT_INPUT_KEY = "sequence_toolbox_transform_result_input"
TRANSFORM_RESULT_MODE_KEY = "sequence_toolbox_transform_result_mode"
TRANSLATION_RESULT_INPUT_KEY = "sequence_toolbox_translation_result_input"


def _analysis_input_is_ready(raw_sequence: str) -> bool:
    """Return whether the top-level DNA input can be submitted for analysis."""
    normalized = normalize_sequence_text(raw_sequence)
    return bool(normalized) and all(base in DNA_IUPAC_ANALYSIS_ALPHABET for base in normalized)


def _tool_input_is_ready(raw_sequence: str, alphabet: set[str], reject_mixed: bool = False) -> bool:
    normalized = normalize_sequence_text(raw_sequence)
    return bool(normalized) and not (reject_mixed and "T" in normalized and "U" in normalized) and all(
        base in alphabet for base in normalized
    )


def _load_transform_example() -> None:
    st.session_state["sequence_toolbox_transform_input"] = "ATGCCGTA"
    st.session_state.pop(TRANSFORM_RESULT_KEY, None)
    st.session_state.pop(TRANSFORM_RESULT_INPUT_KEY, None)
    st.session_state.pop(TRANSFORM_RESULT_MODE_KEY, None)
    st.session_state.pop("sequence_toolbox_transform_error", None)


def _load_translation_example() -> None:
    st.session_state["sequence_toolbox_translation_input"] = "ATGAAATAA"
    st.session_state.pop(TRANSLATION_RESULT_KEY, None)
    st.session_state.pop(TRANSLATION_RESULT_INPUT_KEY, None)
    st.session_state.pop("sequence_toolbox_translation_error", None)

def _topology_labels() -> dict[str, str]:
    return {
        SequenceTopology.UNKNOWN.value: _t("runtime.unknown"),
        SequenceTopology.LINEAR.value: _t("runtime.linear"),
        SequenceTopology.CIRCULAR.value: _t("runtime.circular"),
    }

_ERROR_MESSAGES = {
    SequenceErrorCode.EMPTY_SEQUENCE: "v1.sequence_tools.empty_input_awaiting_valid_dna_input_before",
    SequenceErrorCode.SEQUENCE_CONTAINS_URACIL: "v1.sequence_tools.sequences_containing_iupac_ambiguous_bases_can_analyzed",
    SequenceErrorCode.INVALID_DNA_CHARACTER: "v1.sequence_tools.invalid_input_dna_analysis_construct_generation_cannot",
    SequenceErrorCode.INVALID_TOPOLOGY: "v1.common.topology",
}

_WARNING_MESSAGES = {
    SequenceWarningCode.AMBIGUOUS_BASES_PRESENT: "v1.sequence_tools.sequences_containing_iupac_ambiguous_bases_can_analyzed",
    SequenceWarningCode.NOT_CONSTRUCT_READY: "v1.sequence_tools.analyzable_but_contains_iupac_ambiguous_bases_not",
}


def run_sequence_analysis(
    raw_sequence: str,
    topology: str | SequenceTopology,
) -> DnaSequenceAnalysisResult:
    """Pass unmodified user input and topology to the formal analysis service."""
    return analyze_dna_sequence(raw_sequence, topology=topology)


def _format_count(value: int | None) -> str:
    """Format one service-provided count for display."""
    return _t("runtime.not_computable") if value is None else f"{value:,}"


def _format_percent(value: float | None) -> str:
    """Format one service-provided percentage without deriving a new metric."""
    return _t("runtime.not_computable") if value is None else f"{value:.2f}%"


def _result_is_current(
    result: DnaSequenceAnalysisResult,
    raw_sequence: str,
    topology: str,
) -> bool:
    """Return whether the stored result belongs to the currently visible inputs."""
    return result.raw_sequence == raw_sequence and result.topology.value == topology


def _clear_analysis() -> None:
    """Clear only Sequence Toolbox widget and result state."""
    st.session_state[SEQUENCE_INPUT_KEY] = ""
    st.session_state[TOPOLOGY_KEY] = SequenceTopology.UNKNOWN.value
    st.session_state.pop(RESULT_KEY, None)


def _render_status(result: DnaSequenceAnalysisResult) -> None:
    """Render the four user-facing analysis states from service flags."""
    if result.errors and result.normalized_length == 0:
        st.info(_t("v1.sequence_tools.empty_input_awaiting_valid_dna_input_before"))
    elif not result.is_valid_for_analysis:
        st.error(_t("v1.sequence_tools.invalid_input_dna_analysis_construct_generation_cannot"))
    elif result.is_construct_ready:
        st.success(
            _t("v1.sequence_tools.analyzable_satisfies_construct_ready_criteria_does_not")
        )
    else:
        st.warning(
            _t("v1.sequence_tools.analyzable_but_contains_iupac_ambiguous_bases_not")
        )


def _render_summary(result: DnaSequenceAnalysisResult) -> None:
    """Render counts and flags returned by the formal service."""
    st.subheader(_t("runtime.analysis_summary"))
    _render_status(result)

    first_row = st.columns(4)
    first_row[0].metric(_t("v1.sequence_tools.analysis_validity"), _t("runtime.valid") if result.is_valid_for_analysis else _t("runtime.invalid"))
    first_row[1].metric(
        _t("v1.sequence_tools.construct_ready"), _t("runtime.yes") if result.is_construct_ready else _t("runtime.no")
    )
    first_row[2].metric(_t("v1.common.topology"), _topology_labels()[result.topology.value])
    first_row[3].metric(_t("v1.sequence_tools.standardized_text_length"), f"{result.normalized_length:,}")

    second_row = st.columns(4)
    second_row[0].metric(_t("v1.sequence_tools.number_valid_bases"), f"{result.valid_base_count:,}")
    second_row[1].metric(_t("v1.sequence_tools.dna_sequence_length"), _format_count(result.sequence_length))
    second_row[2].metric(
        _t("v1.sequence_tools.number_non_ambiguous_bases"), _format_count(result.unambiguous_base_count)
    )
    second_row[3].metric(_t("v1.sequence_tools.number_ambiguous_bases"), _format_count(result.ambiguous_base_count))


def _render_gc(result: DnaSequenceAnalysisResult) -> None:
    """Render the service-provided GC metrics with explicit denominators."""
    st.subheader(_t("runtime.gc_metrics"))
    if not result.is_valid_for_analysis:
        st.info(_t("v1.sequence_tools.no_valid_gc_content_result_available_input"))
        return

    if result.ambiguous_base_count:
        columns = st.columns(3)
        columns[0].metric(_t("v1.sequence_tools.gc_count"), _format_count(result.gc_count))
        columns[1].metric(
            _t("v1.sequence_tools.gc_over_full_iupac_compliant_length"),
            _format_percent(result.gc_percent_total),
        )
        columns[2].metric(
            _t("v1.sequence_tools.gc_c_g_t_non_ambiguous_bases"),
            _format_percent(result.gc_percent_unambiguous),
        )
        st.warning(_t("v1.sequence_tools.ambiguous_bases_cause_differences_gc_interpretation_review"))
        return

    columns = st.columns(2)
    columns[0].metric(_t("v1.sequence_tools.gc_count"), _format_count(result.gc_count))
    columns[1].metric(_t("v1.sequence_tools.gc_percentage"), _format_percent(result.gc_percent_total))
    st.caption(_t("v1.sequence_tools.sequence_contains_c_g_t_only_total"))


def _render_findings(result: DnaSequenceAnalysisResult) -> None:
    """Render structured service findings and invalid character positions."""
    st.subheader(_t("runtime.findings"))
    if not result.errors and not result.warnings:
        st.success(_t("v1.sequence_tools.no_errors_warnings_returned"))
    for finding in result.errors:
        message = _t(_ERROR_MESSAGES.get(finding.code, ""), default=finding.message)
        st.error(f"{finding.code.value}: {message}")
    for finding in result.warnings:
        message = _t(_WARNING_MESSAGES.get(finding.code, ""), default=finding.message)
        st.warning(f"{finding.code.value}: {message}")

    if result.invalid_characters:
        st.markdown(_t("v1.sequence_tools.invalid_character_position"))
        for item in result.invalid_characters:
            st.markdown(
                f"- Character `{item.character}`; zero-based position `{item.position}`; "
                f"user position (one-based) `{item.position + 1}`"
            )


def _render_transforms() -> None:
    """Render explicit, read-only DNA/RNA conversion."""
    st.subheader(_t("v1.sequence_tools.dna_rna_conversion"))
    st.caption(_t("v1.sequence_tools.during_conversion_whitespace_characters_will_removed_all"))
    raw = st.text_area(_t("v1.sequence_tools.sequence_conversion"), key="sequence_toolbox_transform_input", height=120)
    mode = st.radio(
        _t("v1.sequence_tools.conversion_direction"),
        options=(SequenceTransformMode.DNA_TO_RNA.value, SequenceTransformMode.RNA_TO_DNA.value),
        format_func=lambda value: _t("v1.sequence_tools.dna_rna_transcription") if value == SequenceTransformMode.DNA_TO_RNA.value else _t("v1.sequence_tools.rna_dna"),
        key="sequence_toolbox_transform_mode",
        horizontal=True,
    )
    transform_alphabet = DNA_IUPAC_ANALYSIS_ALPHABET if mode == SequenceTransformMode.DNA_TO_RNA.value else RNA_IUPAC_ALPHABET
    transform_ready = _tool_input_is_ready(raw, transform_alphabet, reject_mixed=True)
    if st.session_state.get(TRANSFORM_RESULT_INPUT_KEY) != raw or st.session_state.get(TRANSFORM_RESULT_MODE_KEY) != mode:
        st.session_state.pop(TRANSFORM_RESULT_KEY, None)
    action_column, example_column = st.columns(2)
    if action_column.button(
        _t("v1.sequence_tools.re_convert") if TRANSFORM_RESULT_KEY in st.session_state else _t("v1.sequence_tools.convert_sequence"),
        key="sequence_toolbox_transform",
        disabled=not transform_ready,
        type="primary",
        use_container_width=True,
    ):
        try:
            st.session_state[TRANSFORM_RESULT_KEY] = transform_dna_rna(raw, mode)
            st.session_state[TRANSFORM_RESULT_INPUT_KEY] = raw
            st.session_state[TRANSFORM_RESULT_MODE_KEY] = mode
            st.session_state.pop("sequence_toolbox_transform_error", None)
        except SequenceTransformError as exc:
            st.session_state.pop(TRANSFORM_RESULT_KEY, None)
            st.session_state["sequence_toolbox_transform_error"] = str(exc)
    example_column.button(_t("v1.common.load_example"), key="sequence_toolbox_transform_example", on_click=_load_transform_example, use_container_width=True)
    if not raw.strip():
        st.session_state.pop(TRANSFORM_RESULT_KEY, None)
        st.session_state.pop(TRANSFORM_RESULT_INPUT_KEY, None)
        st.session_state.pop(TRANSFORM_RESULT_MODE_KEY, None)
        st.session_state.pop("sequence_toolbox_transform_error", None)
    if "sequence_toolbox_transform_error" in st.session_state:
        st.error(_t("v1.sequence_tools.conversion_failed_check_sequence_characters_selected_conversion"))
    elif TRANSFORM_RESULT_KEY in st.session_state and st.session_state.get(TRANSFORM_RESULT_INPUT_KEY) == raw:
        st.code(st.session_state[TRANSFORM_RESULT_KEY], language="text")
        st.caption(_t("v1.sequence_tools.results_non_persistent_will_not_written_project"))


def _render_translation_and_orfs() -> None:
    """Render shared-service translation and the stable forward ORF table."""
    st.subheader(_t("v1.sequence_tools.translation_orf_analysis"))
    raw = st.text_area(_t("v1.sequence_tools.dna_sequence_used_translation_orf_detection"), key="sequence_toolbox_translation_input", height=120)
    strand = st.radio(_t("v1.common.strand_orientation"), options=("+", "-"), format_func=lambda value: _t("v1.sequence_tools.forward_strand") if value == "+" else _t("v1.sequence_tools.reverse_complement_strand"), horizontal=True, key="sequence_toolbox_translation_strand")
    frame = st.selectbox(_t("v1.common.reading_frame"), options=(1, 2, 3), key="sequence_toolbox_translation_frame")
    stop_rule = st.selectbox(_t("v1.sequence_tools.stop_codon_display"), options=("include", "trim_terminal"), format_func=lambda value: _t("v1.sequence_tools.retain") if value == "include" else _t("v1.sequence_tools.remove_terminal"), key="sequence_toolbox_stop_rule")
    action_column, example_column = st.columns(2)
    if action_column.button(
        _t("v1.sequence_tools.re_translate") if TRANSLATION_RESULT_KEY in st.session_state else _t("v1.sequence_tools.translate_selected_reading_frame"),
        key="sequence_toolbox_translate",
        disabled=not _tool_input_is_ready(raw, DNA_IUPAC_ANALYSIS_ALPHABET),
        type="primary",
        use_container_width=True,
    ):
        try:
            st.session_state[TRANSLATION_RESULT_KEY] = translate_frame(raw, strand, frame, stop_rule)
            st.session_state[TRANSLATION_RESULT_INPUT_KEY] = raw
            st.session_state.pop("sequence_toolbox_translation_error", None)
        except (TypeError, ValueError) as exc:
            st.session_state.pop(TRANSLATION_RESULT_KEY, None)
            st.session_state["sequence_toolbox_translation_error"] = str(exc)
    example_column.button(_t("v1.common.load_example"), key="sequence_toolbox_translation_example", on_click=_load_translation_example, use_container_width=True)
    if not raw.strip():
        st.session_state.pop(TRANSLATION_RESULT_KEY, None)
        st.session_state.pop(TRANSLATION_RESULT_INPUT_KEY, None)
        st.session_state.pop("sequence_toolbox_translation_error", None)
    if "sequence_toolbox_translation_error" in st.session_state:
        st.error(_t("v1.sequence_tools.translation_failed_check_dna_sequence_strand_orientation"))
    elif TRANSLATION_RESULT_KEY in st.session_state and st.session_state.get(TRANSLATION_RESULT_INPUT_KEY) == raw:
        strand_label = _t("v1.sequence_tools.forward_strand") if strand == "+" else _t("v1.sequence_tools.reverse_complement_strand")
        st.markdown(f"{_t('v1.sequence_tools.strand_orientation', value=strand_label)}")
        st.markdown(f"{_t('v1.sequence_tools.reading_frame', value=frame)}")
        st.markdown(_t("v1.sequence_tools.amino_acid_sequence"))
        st.code(st.session_state[TRANSLATION_RESULT_KEY], language="text")
        st.caption(_t("v1.sequence_tools.stop_codon_display_with_value", value=_t("v1.sequence_tools.retain") if stop_rule == "include" else _t("v1.sequence_tools.remove_terminal")))

    st.markdown(_t("v1.sequence_tools.orf_detection_results"))
    st.caption(_t("v1.sequence_tools.coordinates_use_1_based_closed_intervals_shared"))
    st.caption(_t("v1.sequence_tools.shared_orf_service_currently_enforces_minimum_orf"))
    if raw.strip():
        try:
            orfs = normalized_orfs(raw)
            if orfs.empty:
                st.info(_t("v1.sequence_tools.no_orf_matching_rules_detected"))
            else:
                st.dataframe(
                    orfs.rename(
                        columns={
                            "strand": _t("v1.common.strand_orientation"),
                            "frame": _t("v1.common.reading_frame"),
                            "nucleotide_start": _t("v1.sequence_tools.nucleotide_start_position"),
                            "nucleotide_end": _t("v1.sequence_tools.nucleotide_end_position"),
                            "nucleotide_length": _t("v1.sequence_tools.nucleotide_length"),
                            "amino_acid_length": _t("v1.sequence_tools.amino_acid_length"),
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
        except (TypeError, ValueError) as exc:
            st.error(_t("v1.sequence_tools.orf_detection_failed_check_dna_sequence"))


def _render_sequences(result: DnaSequenceAnalysisResult) -> None:
    """Render normalized and reverse-complement fields returned by the service."""
    st.subheader(_t("runtime.sequence_normalized"))
    st.caption(_t("v1.sequence_tools.service_only_removes_whitespace_converts_ascii_alphabetic"))
    if result.normalized_sequence:
        st.code(result.normalized_sequence, language="text", wrap_lines=True)
    else:
        st.info(_t("v1.sequence_tools.standardized_sequence_empty"))

    st.subheader(_t("v1.sequence_tools.reverse_complement"))
    if result.reverse_complement is None:
        st.info(_t("v1.sequence_tools.input_not_valid_dna_iupac_analytical_grade"))
    else:
        st.code(result.reverse_complement, language="text", wrap_lines=True)


def render() -> None:
    """Render the first formal Sequence Toolbox page."""
    st.title(_t("v1.common.sequence_tools"))
    st.caption(_t("v1.sequence_tools.basic_dna_sequence_analysis_conversion"))
    st.info(_t("v1.sequence_tools.sequences_containing_iupac_ambiguous_bases_can_analyzed"))

    raw_sequence = st.text_area(
        _t("v1.sequence_tools.dna_sequence"),
        key=SEQUENCE_INPUT_KEY,
        height=180,
        placeholder=_t("v1.sequence_tools.paste_dna_sequence_supports_multiline_input_mixed"),
    )
    topology = st.selectbox(
        _t("v1.common.topology"),
        options=tuple(_topology_labels()),
        format_func=_topology_labels().__getitem__,
        key=TOPOLOGY_KEY,
    )

    action_columns = st.columns(2)
    analysis_input_is_ready = _analysis_input_is_ready(raw_sequence)
    if not analysis_input_is_ready:
        st.session_state.pop(RESULT_KEY, None)
        prompt = _t("v1.sequence_tools.empty_input_awaiting_valid_dna_input_before") if not raw_sequence.strip() else _t("v1.sequence_tools.invalid_input_dna_analysis_construct_generation_cannot")
        st.info(prompt)
    analyze_clicked = action_columns[0].button(
        _t("v1.sequence_tools.analyze_sequence"),
        type="primary",
        key="sequence_toolbox_analyze",
        disabled=not analysis_input_is_ready,
        use_container_width=True,
    )
    action_columns[1].button(
        _t("v1.common.clear_all"),
        key="sequence_toolbox_clear",
        use_container_width=True,
        on_click=_clear_analysis,
    )

    if analyze_clicked:
        st.session_state[RESULT_KEY] = run_sequence_analysis(raw_sequence, topology)

    result = st.session_state.get(RESULT_KEY)
    if isinstance(result, DnaSequenceAnalysisResult) and not _result_is_current(result, raw_sequence, topology):
        st.info(_t("v1.sequence_tools.input_topology_changed_re_analyze_update_results"))

    st.divider()
    transform_tab, translation_tab = st.tabs((_t("v1.sequence_tools.dna_rna_conversion"), _t("v1.sequence_tools.translation_orf_analysis")))
    with transform_tab:
        _render_transforms()
    with translation_tab:
        _render_translation_and_orfs()

    result = st.session_state.get(RESULT_KEY)
    if not isinstance(result, DnaSequenceAnalysisResult):
        return
    if not _result_is_current(result, raw_sequence, topology):
        st.info(_t("v1.sequence_tools.input_topology_changed_re_analyze_update_results_message"))
        return

    _render_summary(result)
    _render_gc(result)
    _render_sequences(result)
    _render_findings(result)


__all__ = ["render", "run_sequence_analysis"]
