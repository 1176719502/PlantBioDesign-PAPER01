"""views/DesignLibrary.py -- Read-only saved design library MVP."""
from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st

from core.i18n import t as _t
from core.session_keys import SK
from services import pathway_repository
from services.design_saver import (
    format_saved_at_display,
    load_wizard_design,
    query_saved_design_detail,
    query_saved_design_summaries,
)
from services.legacy_snapshot_adapter import normalize_legacy_snapshot
from services.status_derivation import normalize_snapshot_status
from views.tool_typography import (
    inject_tool_typography_css,
    render_compact_summary_cards,
    render_help_text,
    render_subsection_heading,
)

SORT_OPTIONS = ("Newest first", "Oldest first")


def _default_library_filters() -> dict[str, str]:
    return {
        "dl_search_query": "",
        "dl_type_filter": "All",
        "dl_sort_order": "Newest first",
    }


def _clear_library_filters() -> None:
    for key, value in _default_library_filters().items():
        st.session_state[key] = value


def _service_sort_order(ui_sort_order: str) -> str:
    return "asc" if ui_sort_order == "Oldest first" else "desc"


def _service_type_filter(ui_type_filter: str) -> str | None:
    return None if ui_type_filter == "All" else ui_type_filter


def _summary_load_key(summary: dict) -> str:
    return str(summary.get("load_key") or "")


def _available_types(summaries: list[dict]) -> list[str]:
    return sorted({str(item.get("type") or "").strip() for item in summaries if str(item.get("type") or "").strip()})


def _query_summaries(search_query: str, type_filter: str, sort_order: str) -> list[dict]:
    return query_saved_design_summaries(
        search=search_query,
        types=_service_type_filter(type_filter),
        sort_by="saved_at",
        sort_order=_service_sort_order(sort_order),
    )


def _status_display_value(status: object, *, is_saved_record: bool = True) -> str:
    if is_saved_record:
        return normalize_snapshot_status(status)
    return str(status or "").strip()


def _format_count(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _detail_summary(detail: dict) -> dict:
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    primers = detail.get("primers") if isinstance(detail.get("primers"), list) else []
    validation_results = detail.get("validation_results") if isinstance(detail.get("validation_results"), list) else []
    load_warnings = detail.get("load_warnings") if isinstance(detail.get("load_warnings"), list) else []
    return {
        "name": detail.get("name") or summary.get("name", ""),
        "gene": summary.get("gene", ""),
        "host": summary.get("host", ""),
        "type": summary.get("type", ""),
        "sequence_length": summary.get("sequence_length", 0),
        "saved_at": format_saved_at_display(summary.get("saved_at", "")),
        "source": detail.get("source") or summary.get("source", ""),
        "status": _status_display_value(summary.get("status")),
        "primers_count": len(primers) if primers else _format_count(metadata.get("n_primers")),
        "validation_issues_count": len(validation_results) if validation_results else _format_count(metadata.get("n_issues")),
        "load_warnings": [str(item) for item in load_warnings if str(item or "").strip()],
    }


def _safe_detail_display_value(value: object, *, placeholder: str | None = None) -> str:
    fallback = placeholder or _t("design_library.not_recorded")
    if value is None:
        return fallback
    if isinstance(value, (dict, list, tuple, set)):
        try:
            text = json.dumps(value, ensure_ascii=True, sort_keys=True)
        except (TypeError, ValueError):
            text = str(value)
    else:
        text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return text if text else fallback


def _review_safe_text(value: object, *, placeholder: str = "No saved review note recorded.") -> str:
    text = _safe_detail_display_value(value, placeholder=placeholder)
    replacements = [
        (r"\bnot\s+recommended\b", "Manual Review Needed"),
        (r"\breview\s+recommended\b", "Documentation Review Needed"),
        (r"\brecommended\b", "Saved review note"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _primer_review_status_display(status: object) -> str:
    raw = _safe_detail_display_value(status, placeholder="Saved Primer Review Note")
    normalized = raw.lower()
    if "not recommended" in normalized:
        return "Manual Review Needed"
    if "review recommended" in normalized:
        return "Documentation Review Needed"
    if "recommended" in normalized:
        return "Saved Primer Review Note"
    if "usable with risk" in normalized or "risk" in normalized:
        return "Manual Follow-up"
    if normalized == "primer status preserved":
        return "Saved Primer Review Note"
    return _review_safe_text(raw, placeholder="Saved Primer Review Note")


def _compact_saved_review_note(notes: object, *, max_chars: int = 96) -> str:
    safe_note = _review_safe_text(notes)
    if safe_note == "No saved review note recorded.":
        return safe_note
    if len(safe_note) > max_chars:
        return "Saved review note recorded; open details for full text."
    return f"Saved review note: {safe_note}"


def _saved_design_detail_rows(detail: dict) -> list[tuple[str, str]]:
    info = _detail_summary(detail)
    not_recorded = _t("design_library.not_recorded")
    no_load_warnings = _t("design_library.no_load_warnings")
    load_warnings = "\n".join(info["load_warnings"]) if info["load_warnings"] else no_load_warnings
    return [
        (_t("design_library.field.name"), _safe_detail_display_value(info["name"], placeholder=not_recorded)),
        (_t("design_library.field.gene"), _safe_detail_display_value(info["gene"], placeholder=not_recorded)),
        (_t("design_library.field.host"), _safe_detail_display_value(info["host"], placeholder=not_recorded)),
        (_t("design_library.field.type"), _safe_detail_display_value(info["type"], placeholder=not_recorded)),
        (_t("design_library.field.sequence_length"), f"{_format_count(info['sequence_length'])} bp"),
        (_t("design_library.field.saved_at"), _safe_detail_display_value(info["saved_at"], placeholder=not_recorded)),
        (_t("design_library.field.source"), _safe_detail_display_value(info["source"], placeholder=not_recorded)),
        (_t("design_library.field.status"), _safe_detail_display_value(info["status"], placeholder=not_recorded)),
        (_t("design_library.metric.primers"), str(_format_count(info["primers_count"]))),
        (_t("design_library.metric.validation_issues"), str(_format_count(info["validation_issues_count"]))),
        (_t("design_library.field.load_warnings"), _safe_detail_display_value(load_warnings, placeholder=no_load_warnings)),
    ]


def _saved_design_detail_groups(detail: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    rows = dict(_saved_design_detail_rows(detail))
    return [
        (
            "Record Summary",
            [
                (_t("design_library.field.name"), rows[_t("design_library.field.name")]),
                (_t("design_library.field.gene"), rows[_t("design_library.field.gene")]),
                (_t("design_library.field.host"), rows[_t("design_library.field.host")]),
                (_t("design_library.field.type"), rows[_t("design_library.field.type")]),
                (_t("design_library.field.sequence_length"), rows[_t("design_library.field.sequence_length")]),
            ],
        ),
        (
            "Saved Context",
            [
                (_t("design_library.field.saved_at"), rows[_t("design_library.field.saved_at")]),
                (_t("design_library.field.source"), rows[_t("design_library.field.source")]),
                (_t("design_library.field.status"), rows[_t("design_library.field.status")]),
                (_t("design_library.field.load_warnings"), rows[_t("design_library.field.load_warnings")]),
            ],
        ),
    ]


def _summary_table_rows(summaries: list[dict]) -> list[dict]:
    return [
        {
            "Name": item.get("name", ""),
            "Gene": item.get("gene", ""),
            "Host": item.get("host", ""),
            "Type": item.get("type", ""),
            "Length (bp)": item.get("sequence_length", 0),
            "Saved At": format_saved_at_display(item.get("saved_at", "")),
            "Source": item.get("source", ""),
            "Status": _status_display_value(item.get("status")),
        }
        for item in summaries
    ]


def _selection_label(summary: dict) -> str:
    name = str(summary.get("name") or "Untitled Design")
    saved_at = format_saved_at_display(summary.get("saved_at"))
    return f"{name} · {saved_at}" if saved_at else name


def _load_into_wizard(load_key: str, display_name: str, change_page) -> None:
    ok, result = load_wizard_design(load_key)
    if not ok:
        st.error(_t("design_library.load_failed", result=result))
        return

    from core.design_session import SessionController
    from services.pathway_wizard_context import clear_pathway_context_for_independent_wizard_entry

    clear_pathway_context_for_independent_wizard_entry()
    ctrl = SessionController()
    ctrl.save(result)
    frame = result.frame if isinstance(result.frame, dict) else {}
    resolved_sequence = frame.get("final_sequence") or result.optimized_seq or result.original_seq
    st.session_state[SK.ACTIVE_HOST] = result.host
    st.session_state[SK.ACTIVE_SEQ] = resolved_sequence
    st.session_state[SK.ACTIVE_FEATURES] = frame.get("features", []) if isinstance(frame.get("features"), list) else []
    st.session_state[SK.ACTIVE_NAME] = display_name
    st.session_state[SK.DASHBOARD_PROJECT] = display_name
    st.session_state.pop("wf_plasmid_png", None)
    st.success(_t("design_library.load_success", name=display_name))
    if change_page is not None:
        change_page("Expression Wizard")


def _compatibility_preview_rows(detail: dict) -> list[tuple[str, object]]:
    normalized = normalize_legacy_snapshot(detail)
    warnings = normalized.get("load_warnings") if isinstance(normalized.get("load_warnings"), list) else []
    return [
        ("Compatibility note", "Legacy snapshot data is a historical documentation record only."),
        ("Review guidance", "Use Expression Wizard Step 6 for current documentation/export review."),
        ("Warnings", "\n".join(str(item) for item in warnings if str(item or "").strip()) or "No compatibility warnings recorded."),
        ("Historical validation data", "Historical validation data present." if normalized.get("has_historical_validation") else "No historical validation data recorded."),
        ("Primer snapshot data", "Primer data is snapshot-only." if normalized.get("has_primer_snapshot") else "No primer snapshot data recorded."),
        ("Historical validation issue count", normalized.get("historical_validation_issue_count", 0)),
        ("Primer snapshot count", normalized.get("primer_snapshot_count", 0)),
        ("Source", normalized.get("source") or "Not recorded"),
        ("Snapshot created at", normalized.get("snapshot_created_at") or "Not recorded"),
    ]


def _render_compatibility_preview(detail: dict) -> None:
    with st.expander("Legacy Snapshot Compatibility"):
        rows = _compatibility_preview_rows(detail)
        st.table(pd.DataFrame(rows, columns=[_t("design_library.detail_field"), _t("design_library.detail_value")]))


def _preview_sequence_value(detail: dict) -> str:
    sequence = str(detail.get("sequence") or "").strip()
    if sequence:
        return sequence
    design_data = detail.get("design_data") if isinstance(detail.get("design_data"), dict) else {}
    frame = detail.get("frame") if isinstance(detail.get("frame"), dict) else {}
    design_frame = design_data.get("frame") if isinstance(design_data.get("frame"), dict) else {}
    return str(
        design_data.get("sequence")
        or frame.get("final_sequence")
        or design_frame.get("final_sequence")
        or design_data.get("optimized_seq")
        or design_data.get("original_seq")
        or ""
    ).strip()


def _first_saved_list_field(*candidates: object) -> list:
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
    return []


def _feature_preview_rows(detail: dict) -> list[dict[str, object]]:
    design_data = detail.get("design_data") if isinstance(detail.get("design_data"), dict) else {}
    frame = detail.get("frame") if isinstance(detail.get("frame"), dict) else {}
    metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    design_frame = design_data.get("frame") if isinstance(design_data.get("frame"), dict) else {}
    features = _first_saved_list_field(
        frame.get("features"),
        detail.get("features"),
        design_data.get("features"),
        design_frame.get("features"),
        metadata.get("features"),
    )
    rows = []
    for index, feature in enumerate(features, start=1):
        if not isinstance(feature, dict):
            continue
        rows.append(
            {
                "#": index,
                "Feature": feature.get("name") or feature.get("label") or feature.get("type") or "Not recorded",
                "Type": feature.get("type") or "Not recorded",
                "Start": feature.get("start", "Not recorded"),
                "End": feature.get("end", "Not recorded"),
                "Notes": feature.get("note") or feature.get("description") or "Review only",
            }
        )
    return rows


def _primer_status_preview_rows(detail: dict) -> list[dict[str, object]]:
    design_data = detail.get("design_data") if isinstance(detail.get("design_data"), dict) else {}
    metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    primers = _first_saved_list_field(detail.get("primers"), design_data.get("primers"), metadata.get("primers"))
    rows = []
    for index, primer in enumerate(primers, start=1):
        if not isinstance(primer, dict):
            continue
        primer_sequence = str(
            primer.get("sequence")
            or primer.get("Forward Primer (5'->3')")
            or primer.get("Reverse Primer (5'->3')")
            or ""
        )
        status = (
            primer.get("status")
            or primer.get("Status")
            or primer.get("recommendation")
            or primer.get("risk_status")
            or primer.get("Quality Grade")
            or "primer status preserved"
        )
        notes = primer.get("notes") or primer.get("message") or primer.get("Quality Reasons") or primer.get("Warnings")
        if isinstance(notes, list):
            notes = "; ".join(str(item) for item in notes if str(item or "").strip())
        rows.append(
            {
                "#": index,
                "Primer": primer.get("name") or primer.get("id") or f"Primer {index}",
                "Length": len(primer_sequence) if primer_sequence else "Not recorded",
                "Review Label": _primer_review_status_display(status),
                "Saved Review Note": _compact_saved_review_note(notes),
            }
        )
    return rows


def _primer_note_detail_rows(detail: dict) -> list[dict[str, object]]:
    design_data = detail.get("design_data") if isinstance(detail.get("design_data"), dict) else {}
    metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    primers = _first_saved_list_field(detail.get("primers"), design_data.get("primers"), metadata.get("primers"))
    rows = []
    for index, primer in enumerate(primers, start=1):
        if not isinstance(primer, dict):
            continue
        notes = primer.get("notes") or primer.get("message") or primer.get("Quality Reasons") or primer.get("Warnings")
        if isinstance(notes, list):
            notes = "; ".join(str(item) for item in notes if str(item or "").strip())
        if not str(notes or "").strip():
            continue
        rows.append(
            {
                "#": index,
                "Primer": primer.get("name") or primer.get("id") or f"Primer {index}",
                "Saved Primer Review Note": _review_safe_text(notes),
            }
        )
    return rows


def _sequence_preview_summary_rows(detail: dict) -> list[tuple[str, object]]:
    info = _detail_summary(detail)
    sequence = _preview_sequence_value(detail)
    return [
        ("Preview type", "documentation-only sequence summary"),
        ("Record", info["name"] or "Not recorded"),
        ("Gene", info["gene"] or "Not recorded"),
        ("Host", info["host"] or "Not recorded"),
        ("Type", info["type"] or "Not recorded"),
        ("Saved at", info["saved_at"] or "Not recorded"),
        ("Local documentation state", info["status"] or "Not recorded"),
        ("Sequence length", f"{len(sequence) or info['sequence_length']} bp"),
        ("Sequence preview", sequence[:80] + ("..." if len(sequence) > 80 else "") if sequence else "Not recorded"),
    ]


def _safe_json_dict(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(str(raw or ""))
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _saved_design_reference_values(detail: dict) -> set[str]:
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
    design_data = detail.get("design_data") if isinstance(detail.get("design_data"), dict) else {}
    values = {
        detail.get("design_id"),
        detail.get("load_key"),
        detail.get("name"),
        summary.get("design_id"),
        summary.get("saved_design_id"),
        summary.get("load_key"),
        summary.get("name"),
        summary.get("display_name"),
        metadata.get("design_id"),
        metadata.get("saved_design_id"),
        metadata.get("display_name"),
        design_data.get("design_id"),
        design_data.get("display_name"),
        design_data.get("design_name"),
    }
    nested_metadata = design_data.get("saved_design_metadata") if isinstance(design_data.get("saved_design_metadata"), dict) else {}
    values.update({nested_metadata.get("design_id"), nested_metadata.get("display_name")})
    return {str(value).strip() for value in values if str(value or "").strip()}


def _linked_project_context_rows(detail: dict) -> list[tuple[str, object]]:
    references = _saved_design_reference_values(detail)
    if not references:
        return []

    rows: list[tuple[str, object]] = []
    try:
        projects = pathway_repository.list_pathway_projects()
    except Exception:
        return []

    for project in projects:
        project_id = project.get("id")
        try:
            links = pathway_repository.list_expression_design_links(project_id)
        except Exception:
            continue
        for link in links:
            snapshot = _safe_json_dict(link.get("design_snapshot_json"))
            snapshot_values = {
                link.get("design_name"),
                snapshot.get("design_id"),
                snapshot.get("saved_design_id"),
                snapshot.get("load_key"),
                snapshot.get("display_name"),
                snapshot.get("design_name"),
                snapshot.get("name"),
            }
            if not references.intersection({str(value).strip() for value in snapshot_values if str(value or "").strip()}):
                continue
            rows = [
                ("Linked project name", project.get("name") or "Not recorded"),
                ("Linked project id or local reference", project_id or "Not recorded"),
                ("Linked snapshot/documentation context", link.get("design_name") or snapshot.get("design_name") or "Not recorded"),
                ("Local documentation state", project.get("status") or "Not recorded"),
                ("Documentation Review Needed", "Manual follow-up cue; documentation-only context and saved primer review state preserved."),
            ]
            step_id = link.get("step_id")
            if step_id:
                rows.insert(2, ("Linked pathway step local reference", step_id))
            rows.append(
                (
                    "Documentation traceability",
                    "This saved design record can be reviewed in linked Pathway Project context; the link supports documentation traceability only.",
                )
            )
            return rows
    return []


def _render_linked_project_context(detail: dict) -> None:
    st.subheader("Linked Project Context")
    st.caption(
        "Linked pathway documentation context from local records only. A saved design record can be reviewed in "
        "linked Pathway Project context for documentation traceability only."
    )
    st.caption(
        "Expression Wizard is the design record subflow. Linked records remain local documentation records; they are "
        "not experimental validation or readiness approval."
    )
    rows = _linked_project_context_rows(detail)
    if rows:
        st.table(pd.DataFrame(rows, columns=[_t("design_library.detail_field"), _t("design_library.detail_value")]))
        st.caption(
            "Documentation review cue: linked project context does not change the saved design record, saved payload "
            "fields, or saved primer review state."
        )
    else:
        st.info("No linked pathway documentation project is recorded for this saved design.")
        st.caption(
            "This saved design record remains available as a local documentation record. This does not change the "
            "saved design record or primer status."
        )


def _render_saved_record_preview(detail: dict) -> None:
    info = _detail_summary(detail)
    st.subheader("Saved Record Review")
    st.caption(
        "Documentation-only preview of existing saved design record fields. Saved design records are local "
        "documentation records from the Expression Wizard design record subflow. Documentation review is needed "
        "before using this record as a reference."
    )
    tabs = st.tabs([
        "Sequence Summary",
        "Feature Summary",
        "Primer Review",
        "Linked Project Context",
        "Saved Review Notes",
        "Boundary",
    ])

    with tabs[0]:
        st.table(pd.DataFrame(_sequence_preview_summary_rows(detail), columns=[_t("design_library.detail_field"), _t("design_library.detail_value")]))
        st.caption(
            "Loaded state preview: local documentation state only; documentation review is needed before reuse as a design reference. "
            "Loading restores saved wizard inputs and outputs without changing linked project context."
        )

    with tabs[1]:
        st.caption("Feature summary is for review only and reflects saved record fields without reinterpretation.")
        feature_rows = _feature_preview_rows(detail)
        if feature_rows:
            st.table(pd.DataFrame(feature_rows))
        else:
            st.info("No saved feature records found in this local documentation state.")

    with tabs[2]:
        st.caption("Primer review labels summarize saved record state only; no primer risk propagation is recalculated here.")
        primer_rows = _primer_status_preview_rows(detail)
        if primer_rows:
            st.table(pd.DataFrame(primer_rows))
            note_rows = _primer_note_detail_rows(detail)
            if note_rows:
                with st.expander("Saved Primer Review Notes"):
                    st.table(pd.DataFrame(note_rows))
        else:
            st.info("No saved primer records found; primer review remains limited to the saved record.")

    with tabs[3]:
        _render_linked_project_context(detail)

    with tabs[4]:
        rows = [
            ("Documentation Review Needed", "Use this saved design record preview as a documentation aid only."),
            ("Local documentation state", info["status"] or "Not recorded"),
            ("Saved review notes", f"{info['validation_issues_count']} saved review note(s) recorded."),
            ("Record boundary", "Local documentation record only; not experimental validation or readiness approval."),
            ("Load warnings", "\n".join(info["load_warnings"]) or "No load warnings recorded."),
        ]
        st.table(pd.DataFrame(rows, columns=[_t("design_library.detail_field"), _t("design_library.detail_value")]))

    with tabs[5]:
        st.warning(
            "Documentation-only saved design record preview. This section reflects the local documentation state of saved fields only. "
            "It is a review aid, not evidence of biological performance, not a suitability decision, and not instructions for lab work."
        )



def _selection_label(summary: dict) -> str:
    name = str(summary.get("name") or "Untitled Design")
    saved_at = format_saved_at_display(summary.get("saved_at"))
    return f"{name} | {saved_at}" if saved_at else name


def _render_detail(detail: dict) -> None:
    if not detail:
        st.info(_t("design_library.detail_missing"))
        return

    info = _detail_summary(detail)
    st.subheader(_t("design_library.detail_title"))
    render_compact_summary_cards(
        [
            (_t("design_library.metric.length"), f"{info['sequence_length']} bp", info["status"]),
            (_t("design_library.metric.primers"), str(info["primers_count"]), "Saved primer rows"),
            (_t("design_library.metric.validation_issues"), str(info["validation_issues_count"]), "Saved review notes"),
        ]
    )

    st.caption("Selected saved design record. Values are displayed for documentation review and traceability.")
    for group_title, rows in _saved_design_detail_groups(detail):
        render_subsection_heading(group_title)
        for field, value in rows:
            st.markdown(f"**{field}:** {value}")
    _render_saved_record_preview(detail)
    _render_compatibility_preview(detail)


def render(change_page=None) -> None:
    """Render the read-only saved design library."""
    inject_tool_typography_css()
    st.title(_t("design_library.title"))
    render_help_text(_t("design_library.subtitle"))

    defaults = _default_library_filters()
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    all_summaries = query_saved_design_summaries(sort_by="saved_at", sort_order="desc")
    filter_cols = st.columns([2.2, 1.15, 1.15, 0.9], gap="small")
    with filter_cols[0]:
        search_query = st.text_input(
            _t("design_library.search_label"),
            key="dl_search_query",
            placeholder=_t("design_library.search_placeholder"),
        )
    with filter_cols[1]:
        type_options = ["All", *_available_types(all_summaries)]
        type_filter = st.selectbox(
            _t("design_library.filter_label"),
            options=type_options,
            key="dl_type_filter",
            format_func=lambda value: _t("design_library.filter_all") if value == "All" else value,
        )
    with filter_cols[2]:
        sort_order = st.selectbox(_t("design_library.sort_label"), options=list(SORT_OPTIONS), key="dl_sort_order")
    with filter_cols[3]:
        st.write("")
        if st.button(_t("design_library.clear_filters"), key="dl_clear_filters_btn", use_container_width=True):
            _clear_library_filters()
            st.rerun()

    summaries = _query_summaries(search_query, type_filter, sort_order)
    st.caption(_t("design_library.results_count", visible=len(summaries), total=len(all_summaries)))

    if not all_summaries:
        st.info(_t("design_library.empty"))
        return
    if not summaries:
        st.info(_t("design_library.no_match"))
        return

    st.dataframe(
        pd.DataFrame(_summary_table_rows(summaries)),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Name": st.column_config.TextColumn(_t("design_library.table.name"), width="large"),
            "Gene": st.column_config.TextColumn(_t("design_library.table.gene"), width="small"),
            "Host": st.column_config.TextColumn(_t("design_library.table.host"), width="medium"),
            "Type": st.column_config.TextColumn(_t("design_library.table.type"), width="small"),
            "Length (bp)": st.column_config.NumberColumn(_t("design_library.table.length"), width="small", format="%d bp"),
            "Saved At": st.column_config.TextColumn(_t("design_library.table.saved_at"), width="medium"),
            "Source": st.column_config.TextColumn(_t("design_library.table.source"), width="small"),
            "Status": st.column_config.TextColumn(_t("design_library.table.status"), width="small"),
        },
    )
    st.caption(_t("design_library.status_clarification"))

    selected_summary = st.selectbox(
        _t("design_library.select_label"),
        options=summaries,
        key="dl_selected_summary",
        format_func=_selection_label,
    )
    load_key = _summary_load_key(selected_summary)
    detail = query_saved_design_detail(load_key) if load_key else {}

    with st.container(border=True):
        _render_detail(detail)
        can_load = bool(detail.get("can_load")) if isinstance(detail, dict) else False
        if st.button(
            _t("design_library.load_button"),
            key="dl_load_into_wizard_btn",
            type="primary",
            disabled=not can_load or not load_key,
        ):
            _load_into_wizard(load_key, str(selected_summary.get("name") or ""), change_page)


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="Design Library", page_icon="BD")
    render(lambda page: st.toast(f"Opening {page}"))
