# -*- coding: utf-8 -*-
"""Step 2 -- Host & Regulatory Elements."""
from __future__ import annotations

import re

import streamlit as st

from core.session_keys import SK
from services.expression_wizard_step2_intake_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE as STEP2_INTAKE_BOUNDARY_NOTE,
    HOST_OPTION_GROUPS,
    TAG_OPTION_GROUPS,
    TAG_POSITION_OPTIONS,
    build_step2_host_tag_readback,
    flatten_grouped_options,
    host_label_for_runtime,
    resolve_host_selection,
    resolve_tag_selection,
    tag_label_for_runtime,
)
from views.wizard_steps._shared import _section_label, _status_panel, _step_header, render_flow_strip


# ---------------------------------------------------------------------------
# Database access delegated to the service layer
# ---------------------------------------------------------------------------

def _db_parts_map_for_host(host: str, part_types: list[str]) -> dict[str, list[dict]]:
    """Delegate grouped host lookups to services.parts_service."""
    try:
        from services.parts_service import query_registry_parts
        records = query_registry_parts(host=host, part_types=part_types, group_by_type=True)
        return records if isinstance(records, dict) else {}
    except Exception:
        return {}


_KINGDOM_LABELS = {
    "prokaryote": ("Bacteria", "#e3f2fd", "#1565c0"),
    "plant_dicot": ("Plant (Dicot)", "#e8f5e9", "#2e7d32"),
    "plant_monocot": ("Plant (Monocot)", "#e8f5e9", "#2e7d32"),
    "plant_delivery": ("Plant Delivery System", "#e8f5e9", "#388e3c"),
    "yeast": ("Yeast", "#fff3e0", "#e65100"),
    "insect": ("Insect Cells", "#fce4ec", "#880e4f"),
    "mammalian": ("Mammalian Cells", "#f3e5f5", "#6a1b9a"),
    "cell_free": ("Cell-Free System", "#f5f5f5", "#424242"),
}


def _kingdom_badge(kingdom: str) -> str:
    label, bg, fg = _KINGDOM_LABELS.get(kingdom, (kingdom.replace("_", " ").title(), "#f5f5f5", "#333"))
    return (
        f"<span style='background:{bg};color:{fg};border:1px solid {fg}33;border-radius:4px;padding:2px 8px;"
        f"font-size:.75rem;font-weight:600;letter-spacing:.4px;text-transform:uppercase;'>{label}</span>"
    )


def _localize_part_name(name: str) -> str:
    return name


def _host_help_text(host: str, rules: dict | None) -> tuple[str, str]:
    """Return short host guidance text for the current selection."""
    if not host:
        return (
            "Select a host system first.",
            "Choose the biological system you want to document so the default regulatory elements can be reviewed in that host context.",
        )

    rules = rules or {}
    induction_note = str(rules.get("promoter_note") or "").strip()
    promoter_name = str(rules.get("promoter") or "host default promoter")
    vector_name = str(rules.get("vector_suggestion") or "suggested vector")
    gc_range = rules.get("gc_optimal") or (40, 65)
    gc_text = f"{gc_range[0]}-{gc_range[1]}%" if isinstance(gc_range, (tuple, list)) and len(gc_range) >= 2 else "host-specific"

    softened_note = _soften_review_note(induction_note)
    return (
        f"Current host: {host}",
        f"Host-linked promoter: {promoter_name}. Reference vector context: {vector_name}. Target CDS GC review window: {gc_text}. "
        + (softened_note[:160] + ("..." if len(softened_note) > 160 else "") if softened_note else "Review the automatically selected parts before continuing."),
    )


def _soften_review_note(note: str) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    try:
        from core.expression_frame_builder import _sanitize_host_copy
        return _sanitize_host_copy(text)
    except Exception:
        replacements = [
            (r"\b[Bb]est\b", "default"),
            (r"\b[Ss]trong\b", "documented"),
            (r"\b[Rr]ecommended\b", "listed"),
            (r"\b[Oo]ptimal\b", "typical"),
            (r"\bhigher expression\b", "documented expression context"),
            (r"\byield can reach\b", "documentation may note"),
            (r"\bhost compatibility\b", "host context"),
        ]
        softened = text
        for pattern, replacement in replacements:
            softened = re.sub(pattern, replacement, softened)
        return softened


def _part_row(label: str, name: str, note: str, seq: str = "") -> str:
    note_short = note[:120] + "\u2026" if len(note) > 120 else note
    seq_preview = ""
    if seq:
        display_seq = seq[:40] + "\u2026" if len(seq) > 40 else seq
        seq_preview = f"<div style='font-family:monospace;font-size:.72rem;color:#6b7280;margin-top:3px;word-break:break-all;'>{display_seq}</div>"
    return (
        f"<div style='padding:9px 12px;border:1px solid #e5e7eb;border-radius:6px;margin-bottom:6px;background:#ffffff;'>"
        f"<div style='font-size:.7rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;'>{label}</div>"
        f"<div style='font-size:.88rem;font-weight:600;color:#111827;margin-top:2px;'>{name}</div>"
        f"<div style='font-size:.78rem;color:#4b5563;margin-top:3px;line-height:1.5;'>{note_short}</div>{seq_preview}</div>"
    )


def _component_context_row(row: dict) -> str:
    category = str(row.get("category") or "Component Library context")
    asset_label = str(row.get("asset_label") or "No recorded Component Library context")
    step2_value = str(row.get("step2_value") or "No Step 2 value recorded")
    context_state = str(row.get("context_state") or "manual follow-up")
    source_status = str(row.get("source_provenance_review") or "manual follow-up")
    review_status = str(row.get("record_review_status") or "manual follow-up")
    follow_up = str(row.get("manual_follow_up") or "Manual follow-up is required in the existing review surface.")
    recorded_context = str(row.get("recorded_context") or "recorded context not provided")
    sequence_metadata = str(row.get("sequence_metadata") or "metadata not recorded")
    return (
        "<div style='padding:9px 12px;border:1px solid #e5e7eb;border-radius:6px;margin-bottom:6px;background:#ffffff;'>"
        f"<div style='font-size:.7rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;'>{category}</div>"
        f"<div style='font-size:.88rem;font-weight:600;color:#111827;margin-top:2px;'>{asset_label}</div>"
        f"<div style='font-size:.76rem;color:#4b5563;margin-top:3px;'>Step 2 recorded value: {step2_value}</div>"
        f"<div style='font-size:.76rem;color:#4b5563;margin-top:3px;'>Recorded context: {recorded_context}</div>"
        f"<div style='font-size:.76rem;color:#374151;margin-top:3px;'><b>Context state:</b> {context_state}; "
        f"<b>source/provenance review:</b> {source_status}; <b>record review:</b> {review_status}; "
        f"<b>sequence metadata:</b> {sequence_metadata}</div>"
        f"<div style='font-size:.76rem;color:#6b7280;margin-top:3px;'>Manual follow-up: {follow_up}</div></div>"
    )


def _component_context_summary(summary: dict) -> str:
    total = int(summary.get("rows_with_recorded_assets") or 0)
    source_review = int(summary.get("source_provenance_review_rows") or 0)
    manual_follow_up = int(summary.get("manual_follow_up_rows") or 0)
    sequence_metadata = int(summary.get("incomplete_sequence_metadata_rows") or 0)
    return (
        "<div style='padding:10px 12px;border:1px solid #dbeafe;border-radius:6px;margin:8px 0;background:#f8fbff;'>"
        "<div style='font-size:.78rem;font-weight:700;color:#1f2937;margin-bottom:6px;'>Compact documentation summary</div>"
        "<div style='display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;'>"
        f"<div style='font-size:.76rem;color:#374151;'><b>Related records found:</b> {total}</div>"
        f"<div style='font-size:.76rem;color:#374151;'><b>Rows needing source/provenance review:</b> {source_review}</div>"
        f"<div style='font-size:.76rem;color:#374151;'><b>Rows needing manual follow-up:</b> {manual_follow_up}</div>"
        f"<div style='font-size:.76rem;color:#374151;'><b>Rows with incomplete sequence metadata:</b> {sequence_metadata}</div>"
        "</div>"
        "<div style='font-size:.74rem;color:#4b5563;margin-top:7px;line-height:1.45;'>"
        "Documentation-only context summary for Step 2 review. Full source/provenance details remain available below; "
        "manual follow-up is required before citing context in project notes."
        "</div></div>"
    )


def _render_component_library_context(host: str, tag: str, rules: dict, elements: dict) -> None:
    try:
        from services.expression_wizard_step2_component_context_presenter import (
            build_step2_component_library_context,
        )
        presenter = build_step2_component_library_context(
            host=host,
            tag=tag,
            rules=rules,
            elements=elements if isinstance(elements, dict) else {},
        )
    except Exception:
        presenter = {
            "title": "Component Library context",
            "rows": [],
            "empty_state": (
                "No Component Library context is recorded for the current Step 2 review surface. "
                "Manual follow-up is required in the existing Component Library or review surfaces before citing context in project notes."
            ),
            "documentation_boundary_note": (
                "Component Library context is read-only recorded context for source/provenance review and manual follow-up. "
                "It is not a biological recommendation."
            ),
        }

    st.divider()
    _section_label(str(presenter.get("title") or "Component Library context"))
    st.caption(str(presenter.get("subtitle") or "Read-only recorded context for source/provenance review and manual follow-up."))
    st.caption(str(presenter.get("documentation_boundary_note") or "This is not a biological recommendation."))

    rows = presenter.get("rows") if isinstance(presenter.get("rows"), list) else []
    if not rows or not presenter.get("rows_with_assets"):
        st.info(str(presenter.get("empty_state") or "No Component Library context is recorded. Manual follow-up is required."))

    summary = presenter.get("summary") if isinstance(presenter.get("summary"), dict) else {}
    st.markdown(_component_context_summary(summary), unsafe_allow_html=True)
    st.caption("Additional context records are hidden by default to keep Step 2 readable.")

    with st.expander("Review all linked component context records", expanded=False):
        for row in rows:
            if isinstance(row, dict):
                st.markdown(_component_context_row(row), unsafe_allow_html=True)


_STEP2_PART_TYPES = {"Promoter", "RBS", "Terminator"}


def _compact_readback_card(readback: dict) -> str:
    required = readback.get("required_manual_review_fields") if isinstance(readback.get("required_manual_review_fields"), list) else []
    required_text = "; ".join(str(item) for item in required[:6])
    if len(required) > 6:
        required_text += f"; +{len(required) - 6} more"
    return (
        "<div style='padding:10px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fbfdff;margin-top:10px;'>"
        "<div style='font-size:.78rem;font-weight:700;color:#111827;margin-bottom:6px;'>Host/tag documentation readback</div>"
        f"<div style='font-size:.76rem;color:#374151;'><b>Selected host/system:</b> {readback.get('selected_host_system') or 'Not recorded'}</div>"
        f"<div style='font-size:.76rem;color:#374151;margin-top:3px;'><b>Selected tag strategy:</b> {readback.get('selected_tag_strategy') or 'Not recorded'}</div>"
        f"<div style='font-size:.76rem;color:#374151;margin-top:3px;'><b>Tag position:</b> {readback.get('tag_position') or 'Not recorded'}</div>"
        f"<div style='font-size:.76rem;color:#374151;margin-top:3px;'><b>Documentation status:</b> {readback.get('documentation_status') or 'Manual review required.'}</div>"
        f"<div style='font-size:.76rem;color:#374151;margin-top:3px;'><b>Required manual review fields:</b> {required_text or 'Manual review fields not recorded.'}</div>"
        f"<div style='font-size:.74rem;color:#4b5563;margin-top:7px;line-height:1.45;'>{readback.get('boundary_note') or STEP2_INTAKE_BOUNDARY_NOTE}</div>"
        "</div>"
    )


def _required_slots_card(slots: list[str]) -> str:
    rows = "".join(
        f"<div style='font-size:.75rem;color:#374151;padding:2px 0;'>- {slot}</div>"
        for slot in slots
    )
    return (
        "<div style='padding:9px 12px;border:1px solid #e5e7eb;border-radius:6px;background:#ffffff;margin-top:8px;'>"
        "<div style='font-size:.74rem;font-weight:700;color:#111827;margin-bottom:4px;'>Host-linked required documentation slots</div>"
        f"{rows}"
        "</div>"
    )


def _candidate_type(candidate: dict) -> str:
    try:
        from services.parts_service import normalize_part_type
        return normalize_part_type(candidate.get("canonical_type") or candidate.get("part_type"))
    except Exception:
        return str(candidate.get("canonical_type") or candidate.get("part_type") or "").strip()


def _candidate_host(candidate: dict) -> str:
    for key in ("host_context", "recommended_host", "organism", "host"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return ""


def _host_compatibility(candidate: dict, selected_host: str) -> tuple[str, str, bool]:
    part_type = _candidate_type(candidate)
    sequence = str(candidate.get("sequence") or "").strip()
    if part_type not in _STEP2_PART_TYPES:
        return "Unsupported type", "Only promoter, RBS/Kozak, and terminator candidates can be used in Step 2.", False
    if not sequence:
        return "Missing sequence", "This candidate has no sequence and cannot be used for Step 2.", False

    host_text = _candidate_host(candidate)
    if not host_text:
        return "Host context unavailable", "This candidate has no documented host context and cannot be applied in the current Step 2 review.", False
    if host_text.strip().lower() == "universal":
        return "Candidate available for review", "This universal entry can be reviewed under any selected host context.", True

    try:
        from services.parts_service import host_to_organism
        selected_organism = host_to_organism(selected_host)
        candidate_organism = host_to_organism(host_text)
    except Exception:
        selected_organism = selected_host
        candidate_organism = host_text

    if candidate_organism.strip().lower() == selected_organism.strip().lower():
        return "Candidate available for review", "This candidate is documented for the selected host context.", True
    return "Host context differs", "This candidate is documented for a different host context and cannot be applied in the current Step 2 review.", False


def _render_step2_candidate_panel(host: str) -> dict | None:
    candidate = st.session_state.get(SK.PARTS_STEP2_CANDIDATE_BRIDGE)
    selected = st.session_state.get(SK.PARTS_STEP2_SELECTED_CANDIDATE)
    if not isinstance(candidate, dict):
        return None

    part_type = _candidate_type(candidate)
    name = str(candidate.get("name") or "Unnamed part").strip()
    sequence = str(candidate.get("sequence") or "").strip()
    host_text = _candidate_host(candidate) or "Unknown"
    length_bp = candidate.get("length_bp") or len(sequence)
    preview = sequence[:80] + ("..." if len(sequence) > 80 else "")
    status_title, status_body, selectable = _host_compatibility(candidate, host)

    st.divider()
    _section_label("Parts Registry candidate")
    st.markdown(f"**Name:** {name}")
    st.markdown(f"**Type:** {part_type or 'Unknown'}")
    st.markdown(f"**Documented host context:** {host_text}")
    st.markdown(f"**Sequence length:** {length_bp} bp")
    st.markdown(f"**Candidate review status:** {status_title}")
    if preview:
        st.code(preview, language="text")

    if selectable:
        st.success(f"{status_title}: {status_body}")
    elif status_title in {"Host context unavailable", "Host context differs"}:
        st.warning(f"{status_title}: {status_body}")
    else:
        st.error(f"{status_title}: {status_body}")

    selected_matches = selectable and isinstance(selected, dict) and selected == candidate
    action_cols = st.columns([1, 1])
    with action_cols[0]:
        if selectable and st.button("Use Candidate Record", key="wf_p2_use_parts_candidate", use_container_width=True):
            st.session_state[SK.PARTS_STEP2_SELECTED_CANDIDATE] = candidate
            selected_matches = True
    with action_cols[1]:
        if st.button("Dismiss", key="wf_p2_dismiss_parts_candidate", use_container_width=True):
            _clear_step2_candidate_state_all()
            st.rerun()

    if selected_matches:
        st.info("Candidate record selected for Step 2 confirmation. Click Confirm host & regulatory elements to apply this documented candidate record.")
        return candidate
    return None


def _clear_step2_candidate_state(clear_bridge: bool = True, clear_selected: bool = True) -> None:
    if clear_bridge:
        st.session_state.pop(SK.PARTS_STEP2_CANDIDATE_BRIDGE, None)
    if clear_selected:
        st.session_state.pop(SK.PARTS_STEP2_SELECTED_CANDIDATE, None)


def _clear_step2_candidate_state_all() -> None:
    _clear_step2_candidate_state(clear_bridge=True, clear_selected=True)


def _selected_candidate_for_confirm(host: str) -> tuple[dict | None, str]:
    bridge_candidate = st.session_state.get(SK.PARTS_STEP2_CANDIDATE_BRIDGE)
    selected_candidate = st.session_state.get(SK.PARTS_STEP2_SELECTED_CANDIDATE)
    if not isinstance(selected_candidate, dict):
        return None, ""
    if not isinstance(bridge_candidate, dict) or selected_candidate != bridge_candidate:
        _clear_step2_candidate_state(clear_bridge=False, clear_selected=True)
        return None, "The selected Parts Registry candidate is stale. Select the candidate again before confirming Step 2."

    status_title, status_body, selectable = _host_compatibility(selected_candidate, host)
    if not selectable:
        _clear_step2_candidate_state(clear_bridge=False, clear_selected=True)
        return None, f"{status_title}: {status_body}"
    return selected_candidate, ""


def _apply_selected_candidate_to_elements(elements: dict, candidate: dict | None) -> dict:
    if not isinstance(candidate, dict):
        return elements
    part_type = _candidate_type(candidate)
    name = str(candidate.get("name") or "").strip()
    sequence = str(candidate.get("sequence") or "").strip()
    if part_type == "Promoter":
        elements["promoter_name"] = name
        elements["promoter_seq"] = sequence
    elif part_type == "RBS":
        elements["rbs_name"] = name
        elements["rbs_seq"] = sequence
    elif part_type == "Terminator":
        elements["terminator_name"] = name
        elements["terminator_seq"] = sequence
    return elements


def page(ctrl) -> None:
    ds = ctrl.get()

    _loaded_elements = ds.elements if isinstance(ds.elements, dict) else {}
    _sync_signature = (
        ds.host or "",
        ds.tag or "",
        _loaded_elements.get("promoter_name", "") or "",
        _loaded_elements.get("promoter_seq", "") or "",
        _loaded_elements.get("rbs_name", "") or "",
        _loaded_elements.get("rbs_seq", "") or "",
        _loaded_elements.get("terminator_name", "") or "",
        _loaded_elements.get("terminator_seq", "") or "",
    )
    if st.session_state.get("_wf_p2_loaded_sync") != _sync_signature:
        for _widget_key in (
            "wf_p2_host",
            "wf_p2_tag",
            "wf_p2_prom",
            "wf_p2_rbs",
            "wf_p2_term",
            "wf_p2_prom_db",
            "wf_p2_rbs_db",
            "wf_p2_term_db",
            "wf_p2_tag_position",
            "wf_p2_custom_host_label",
            "wf_p2_custom_tag_label",
            "wf_p2_manual_source_note",
        ):
            st.session_state.pop(_widget_key, None)
        st.session_state["_wf_p2_loaded_sync"] = _sync_signature

    _step_header(
        2,
        "Host & Regulatory Elements",
        "Record plant species/host context and review plant-facing regulatory element documentation for the current CDS.",
        [
            "Select the expression host and protein tag.",
            "Plant MVP context: plant species, target tissue/organ, expression mode, plant promoter, terminator, and selectable marker/reporter context.",
            "Review the host-linked regulatory elements.",
            "Override defaults in the advanced panel if needed.",
        ],
    )

    try:
        from core.expression_frame_builder import get_host_rules
    except Exception:
        get_host_rules = None

    _host_options, _host_selectable = flatten_grouped_options(HOST_OPTION_GROUPS)
    _saved_host_label = host_label_for_runtime(ds.host) or _host_selectable[0]
    _host_default_idx = _host_options.index(_saved_host_label)
    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        _section_label("Input panel")
        st.caption("Record the host/system and tag strategy as documentation inputs for review.")
        raw_host = st.selectbox(
            "Expression host/system documentation context",
            options=_host_options,
            index=_host_default_idx,
            key="wf_p2_host",
            label_visibility="collapsed",
        )
        host_label = raw_host if raw_host in _host_selectable else _saved_host_label
        host_selection = resolve_host_selection(host_label)
        host = str(host_selection.get("runtime_host") or "")

        custom_host_label = ""
        if host_selection.get("requires_manual_entry"):
            custom_host_label = st.text_input(
                "Custom host label (documentation placeholder)",
                value="",
                placeholder="Record custom/manual host context in project notes",
                key="wf_p2_custom_host_label",
            )
            st.caption("Custom host labels are shown for review only in this batch and are not saved as new host schema fields.")

        try:
            _host_rules_for_tags = get_host_rules(host) if host and get_host_rules else {}
            tag_opts = list(_host_rules_for_tags["tag_options"].keys())
        except Exception:
            _host_rules_for_tags = {}
            tag_opts = ["No tag"]
        if not tag_opts:
            tag_opts = ["No tag"]
        _tag_options, _tag_selectable = flatten_grouped_options(TAG_OPTION_GROUPS)
        _saved_tag_label = tag_label_for_runtime(ds.tag)
        _tag_default_idx = _tag_options.index(_saved_tag_label) if _saved_tag_label in _tag_options else _tag_options.index("No fusion tag")
        raw_tag = st.selectbox("Fusion tag strategy", _tag_options, index=_tag_default_idx, key="wf_p2_tag")
        tag_label = raw_tag if raw_tag in _tag_selectable else _saved_tag_label
        tag_selection = resolve_tag_selection(tag_label, tag_opts)
        tag = str(tag_selection.get("runtime_tag") or "No tag")
        tag_position_default = tag_selection.get("default_position")
        _tag_position_index = TAG_POSITION_OPTIONS.index(tag_position_default) if tag_position_default in TAG_POSITION_OPTIONS else TAG_POSITION_OPTIONS.index("Not recorded")
        tag_position = st.selectbox("Tag position documentation", TAG_POSITION_OPTIONS, index=_tag_position_index, key="wf_p2_tag_position")
        custom_tag_label = ""
        if tag_selection.get("requires_manual_entry"):
            custom_tag_label = st.text_input(
                "Custom tag label (documentation placeholder)",
                value="",
                placeholder="Record custom/manual tag source in project notes",
                key="wf_p2_custom_tag_label",
            )
        manual_source_note = st.text_input(
            "Manual source/provenance note (page-session only)",
            value="",
            placeholder="Record source/provenance follow-up in existing review notes",
            key="wf_p2_manual_source_note",
        )
        if ds.tag and ds.tag not in tag_opts and not tag_selection.get("directly_mapped"):
            st.warning(f"Saved tag '{ds.tag}' is not mapped for **{host or host_label}** and is shown as documentation review context only.")

        helper_title, helper_body = _host_help_text(host, _host_rules_for_tags)
        _status_panel(helper_title, helper_body, tone="info")
        render_flow_strip(
            [
                ("Input", "Host/system, tag strategy, and source/provenance notes"),
                ("Readback", "Documentation-only status and required review slots"),
            ]
        )
        readback = build_step2_host_tag_readback(
            host_selection=host_selection,
            tag_selection=tag_selection,
            tag_position=tag_position,
            custom_host_label=custom_host_label,
            custom_tag_label=custom_tag_label,
            manual_source_note=manual_source_note,
        )
        st.markdown(_compact_readback_card(readback), unsafe_allow_html=True)
        st.markdown(_required_slots_card(list(host_selection.get("required_slots") or [])), unsafe_allow_html=True)

        try:
            _rules = _host_rules_for_tags or get_host_rules(host)
            _prom_note_lc = _rules.get("promoter_note", "").lower()
            if "iptg" in _prom_note_lc:
                _induction = "IPTG induction"
            elif "galactose" in _prom_note_lc:
                _induction = "Galactose induction"
            elif "methanol" in _prom_note_lc:
                _induction = "Methanol induction"
            elif "arabinose" in _prom_note_lc:
                _induction = "Arabinose induction"
            elif "constitutive" in _prom_note_lc:
                _induction = "Constitutive expression"
            elif "light" in _prom_note_lc:
                _induction = "Light induction"
            else:
                _induction = "See promoter notes"
            st.markdown(
                f"<div style='background:#f8f9fb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin-top:10px;'>"
                f"<div style='margin-bottom:6px;'>{_kingdom_badge(_rules.get('kingdom', ''))}</div>"
                f"<div style='font-size:.78rem;color:#374151;'><b>Vector review note:</b> {_rules.get('vector_suggestion', 'N/A')}</div>"
                f"<div style='font-size:.78rem;color:#374151;margin-top:4px;'><b>Target GC review range:</b> {_rules.get('gc_optimal', (40, 65))[0]}\u2013{_rules.get('gc_optimal', (40, 65))[1]}%</div>"
                f"<div style='margin-top:5px;font-size:.78rem;color:#374151;'><b>Induction mode:</b> {_induction}</div></div>",
                unsafe_allow_html=True,
            )
        except Exception:
            pass

    with c2:
        _status_panel(
            "Host-linked elements",
            (
                "Review the host-linked regulatory element documentation slots below. If you need a different promoter, "
                "RBS/Kozak, or terminator label, use the advanced overrides section."
                if host
                else "Select a mapped host/system option to show host-linked regulatory element slots."
            ),
            tone="info" if host else "warn",
        )
        try:
            if not host:
                raise ValueError("A mapped host is required for host-linked element display.")
            _r = get_host_rules(host)
            _kd = _r.get("kingdom", "")
            st.markdown(_part_row("Promoter", _r["promoter"], _soften_review_note(_r.get("promoter_note", "")), _r.get("promoter_seq", "")), unsafe_allow_html=True)
            _rbs_label = "RBS / Shine-Dalgarno" if _kd == "prokaryote" else "Kozak / Translation-initiation signal"
            st.markdown(_part_row(_rbs_label, _r["rbs"], _soften_review_note(_r.get("rbs_note", "")), _r.get("rbs_seq", "")), unsafe_allow_html=True)
            st.markdown(_part_row("Terminator", _r["terminator"], _soften_review_note(_r.get("terminator_note", "")), _r.get("terminator_seq", "")), unsafe_allow_html=True)
            _render_component_library_context(host, tag, _r, ds.elements if isinstance(ds.elements, dict) else {})
        except Exception:
            _status_panel("Host-linked data unavailable", "Host-linked elements are temporarily unavailable for this host. You can still configure them manually in the advanced section.", tone="info")

        with st.expander("Advanced overrides", expanded=False):
            st.caption(
                "Leave a field empty to keep the host default. "
                "Selecting a Part Registry entry replaces the real sequence used in the construct. "
                "Typing a display name only changes labels and metadata unless a registry-backed sequence is also selected."
            )

            prom_seq = ""
            _db_parts = _db_parts_map_for_host(host, ["Promoter", "RBS", "Terminator"])

            _db_proms = _db_parts.get("Promoter", [])
            if _db_proms:
                _prom_opts = [""] + [p["name"] for p in _db_proms]
                _prom_idx = _prom_opts.index(ds.elements.get("promoter_name", "")) if ds.elements.get("promoter_name", "") in _prom_opts else 0
                _prom_sel = st.selectbox(
                    "Promoter sequence override (Part Registry)",
                    _prom_opts,
                    index=_prom_idx,
                    key="wf_p2_prom_db",
                    format_func=lambda x: "Use host default sequence" if x == "" else x,
                )
                if _prom_sel:
                    _prom_rec = next((p for p in _db_proms if p["name"] == _prom_sel), None)
                    if _prom_rec:
                        st.caption(f"Sequence applied to construct: {_prom_rec['sequence'][:40]}... ({_prom_rec.get('length_bp', len(_prom_rec['sequence']))} bp)")
                        prom_seq = _prom_rec["sequence"]
                prom = _prom_sel
                _ = st.text_input(
                    "Promoter display name (label only)",
                    value=ds.elements.get("promoter_name", ""),
                    placeholder="For example: T7 Promoter",
                    key="wf_p2_prom",
                )
                if _:
                    prom = _
            else:
                st.caption("No promoter registry entry is available for this host. The field below only changes labels and metadata.")
                prom = st.text_input(
                    "Promoter display name (label only)",
                    value=ds.elements.get("promoter_name", ""),
                    placeholder="For example: T7 Promoter",
                    key="wf_p2_prom",
                )

            rbs_seq = ""
            _db_rbs = _db_parts.get("RBS", [])
            if _db_rbs:
                _rbs_opts = [""] + [p["name"] for p in _db_rbs]
                _rbs_idx = _rbs_opts.index(ds.elements.get("rbs_name", "")) if ds.elements.get("rbs_name", "") in _rbs_opts else 0
                _rbs_sel = st.selectbox(
                    "RBS / Kozak sequence override (Part Registry)",
                    _rbs_opts,
                    index=_rbs_idx,
                    key="wf_p2_rbs_db",
                    format_func=lambda x: "Use host default sequence" if x == "" else x,
                )
                if _rbs_sel:
                    _rbs_rec = next((p for p in _db_rbs if p["name"] == _rbs_sel), None)
                    if _rbs_rec:
                        st.caption(f"Sequence applied to construct: {_rbs_rec['sequence'][:40]}... ({_rbs_rec.get('length_bp', len(_rbs_rec['sequence']))} bp)")
                        rbs_seq = _rbs_rec["sequence"]
                rbs = _rbs_sel
                _ = st.text_input(
                    "RBS / Kozak display name (label only)",
                    value=ds.elements.get("rbs_name", ""),
                    placeholder="For example: Shine-Dalgarno B0034",
                    key="wf_p2_rbs",
                )
                if _:
                    rbs = _
            else:
                st.caption("No RBS/Kozak registry entry is available for this host. The field below only changes labels and metadata.")
                rbs = st.text_input(
                    "RBS / Kozak display name (label only)",
                    value=ds.elements.get("rbs_name", ""),
                    placeholder="For example: Shine-Dalgarno B0034",
                    key="wf_p2_rbs",
                )

            term_seq = ""
            _db_terms = _db_parts.get("Terminator", [])
            if _db_terms:
                _term_opts = [""] + [p["name"] for p in _db_terms]
                _term_idx = _term_opts.index(ds.elements.get("terminator_name", "")) if ds.elements.get("terminator_name", "") in _term_opts else 0
                _term_sel = st.selectbox(
                    "Terminator sequence override (Part Registry)",
                    _term_opts,
                    index=_term_idx,
                    key="wf_p2_term_db",
                    format_func=lambda x: "Use host default sequence" if x == "" else x,
                )
                if _term_sel:
                    _term_rec = next((p for p in _db_terms if p["name"] == _term_sel), None)
                    if _term_rec:
                        st.caption(f"Sequence applied to construct: {_term_rec['sequence'][:40]}... ({_term_rec.get('length_bp', len(_term_rec['sequence']))} bp)")
                        term_seq = _term_rec["sequence"]
                term = _term_sel
                _ = st.text_input(
                    "Terminator display name (label only)",
                    value=ds.elements.get("terminator_name", ""),
                    placeholder="For example: rrnB T1 Terminator",
                    key="wf_p2_term",
                )
                if _:
                    term = _
            else:
                st.caption("No terminator registry entry is available for this host. The field below only changes labels and metadata.")
                term = st.text_input(
                    "Terminator display name (label only)",
                    value=ds.elements.get("terminator_name", ""),
                    placeholder="For example: rrnB T1 Terminator",
                    key="wf_p2_term",
                )

    selected_parts_candidate = _render_step2_candidate_panel(host)

    _has_downstream = bool((isinstance(ds.frame, dict) and ds.frame) or ds.optimized_seq or ds.primers or ds.validation_results)
    _pending_preview = {
        "promoter_name": prom,
        "promoter_seq": prom_seq,
        "rbs_name": rbs,
        "rbs_seq": rbs_seq,
        "terminator_name": term,
        "terminator_seq": term_seq,
    }
    _pending_preview = _apply_selected_candidate_to_elements(_pending_preview, selected_parts_candidate)
    _pending_change = (
        ds.host != host
        or ds.tag != tag
        or ds.elements.get("promoter_name", "") != _pending_preview["promoter_name"]
        or ds.elements.get("rbs_name", "") != _pending_preview["rbs_name"]
        or ds.elements.get("terminator_name", "") != _pending_preview["terminator_name"]
        or ds.elements.get("promoter_seq", "") != _pending_preview["promoter_seq"]
        or ds.elements.get("rbs_seq", "") != _pending_preview["rbs_seq"]
        or ds.elements.get("terminator_seq", "") != _pending_preview["terminator_seq"]
    )
    if _pending_change and _has_downstream:
        st.info("**Unsaved host changes detected.** Saving this step will invalidate downstream frame, primer, and validation results so they can be rebuilt with the new configuration.")

    step2_ready = bool(host)
    _status_panel(
        "Host selection recorded for this step" if step2_ready else "A host selection is still required",
        "Confirm this step to carry the selected host context into expression-frame assembly." if step2_ready else "Select an expression host before continuing.",
        tone="info" if step2_ready else "warn",
    )

    if step2_ready:
        st.caption(
            "Tip: If the selected host does not match your expected promoter system, save Step 2 now, then revisit the advanced overrides before rebuilding Step 3."
        )

    if st.button(
        "Confirm host & regulatory elements",
        type="primary",
        key="wf_p2_next",
        use_container_width=True,
        disabled=not step2_ready,
        help="Select an expression host before continuing." if not step2_ready else "",
    ):
        if not host:
            st.error("Select an expression host before continuing.")
        else:
            selected_parts_candidate, candidate_error = _selected_candidate_for_confirm(host)
            if candidate_error:
                st.error(candidate_error)
                return

            _pending_elements = {
                "promoter_name": prom,
                "promoter_seq": prom_seq,
                "rbs_name": rbs,
                "rbs_seq": rbs_seq,
                "terminator_name": term,
                "terminator_seq": term_seq,
            }
            _pending_elements = _apply_selected_candidate_to_elements(_pending_elements, selected_parts_candidate)
            _inputs_changed = (
                ds.host != host
                or ds.tag != tag
                or ds.elements.get("promoter_name", "") != _pending_elements["promoter_name"]
                or ds.elements.get("rbs_name", "") != _pending_elements["rbs_name"]
                or ds.elements.get("terminator_name", "") != _pending_elements["terminator_name"]
                or ds.elements.get("promoter_seq", "") != _pending_elements["promoter_seq"]
                or ds.elements.get("rbs_seq", "") != _pending_elements["rbs_seq"]
                or ds.elements.get("terminator_seq", "") != _pending_elements["terminator_seq"]
            )
            if _inputs_changed:
                ds.frame = {}
                ds.optimized_seq = ""
                ds.primers = []
                ds.validation_results = []
            ds.host = host
            ds.tag = tag
            ds.elements = _pending_elements
            from core.session_keys import SK
            st.session_state[SK.ACTIVE_HOST] = host
            _clear_step2_candidate_state_all()
            ctrl.save(ds)
            ctrl.advance()
