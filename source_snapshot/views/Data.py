from __future__ import annotations

import io
import re
from datetime import date

import pandas as pd
import streamlit as st

from core.i18n import t as _t
from core.i18n import get_language as _get_language
from core.database import (
    ALLOWED_ORGANISMS,
    ALLOWED_TYPES,
    add_part,
    add_parts_batch,
    delete_part,
    get_existing_names,
    update_part,
)
from services.local_design_asset_catalog_service import (
    filter_by_asset_type as filter_local_design_assets_by_type,
    load_seed_catalog as load_local_design_asset_seed_catalog,
    search_assets as search_local_design_assets,
    summarize_catalog_inventory as summarize_local_design_asset_inventory,
    summarize_counts_by_asset_type as summarize_local_design_asset_counts,
    summarize_review_status as summarize_local_design_asset_review_status,
)
from services.component_library_asset_readback_presenter import (
    build_component_library_asset_readback_presenter,
)
from services.component_library_contract_crosswalk_presenter import (
    build_component_library_contract_crosswalk_presenter,
)
from services.component_library_followup_queue_presenter import (
    build_component_library_followup_queue_presenter,
    filter_followup_queue_rows,
)
from services.component_library_slot_browse_presenter import (
    build_component_library_slot_browse_presenter,
)
from services.component_library_workflow_entry_presenter import (
    ALL_FOLLOWUP_FILTER,
    ALL_SLOT_FILTER,
    ALL_SOURCE_FILTER,
    ALL_TYPE_FILTER,
    build_component_library_workflow_entry_presenter,
)
from services.host_chassis_context_presenter import summarize_asset_host_chassis_context
from services.parts_service import get_all_parts_cached, normalize_part_type
from views.PartsRegistryBrowse import render_panel as render_read_only_parts_catalog
from views.PlantPromoterCatalog import render as render_plant_promoter_catalog
from services.tool_artifact_library_presenter import (
    ARTIFACT_DELETE_CONFIRMATION_COPY,
    ARTIFACT_DETAIL_PREVIEW_COPY,
    ARTIFACT_LIBRARY_SAFETY_COPY,
    ARTIFACT_LIBRARY_WORKFLOW_COPY,
    artifact_detail_preview_labels,
    artifact_library_empty_state,
    filter_documentation_artifacts,
)
from services.tool_artifact_service import (
    delete_tool_artifact,
    list_tool_artifacts,
    raw_payload_preview,
    readable_payload_summary,
)
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_tool_header,
    render_tool_intro,
)

_TAB_LABELS: dict[str, str] = {
    "Promoter": _t("data.tab.promoter"),
    "RBS": "RBS",
    "CDS": "CDS",
    "Terminator": _t("data.tab.terminator"),
    "Vector": _t("data.tab.vector"),
}

_PART_TYPE_DISPLAY_KEYS = {
    "Promoter": "data.part_type.promoter",
    "RBS": "data.part_type.rbs",
    "CDS": "data.part_type.cds",
    "Terminator": "data.part_type.terminator",
    "Vector": "data.part_type.vector",
}


def _part_type_label(value: str) -> str:
    return _t(_PART_TYPE_DISPLAY_KEYS.get(value, ""), default=value) if value else value

_REGISTRY_MUTATION_NOTICE = (
    "Parts Registry helps you browse, add, and document local DNA part reference records for design support. "
    "Input: reference metadata, optional DNA sequence, FASTA uploads, or search filters. "
    "Output: documentation-only registry records, table previews, and optional transient Wizard Step 2 candidates. "
    "Next step: select a record to view details, use eligible promoter/RBS/terminator records as Step 2 candidates, or add a reference record. "
    "Registry entries do not certify experiment-use state, forecast yield, tune pathways, or provide wet-lab protocols."
)

DATA_SURFACE_SEPARATION_COPY = (
    "Component Library brings together separate documentation surfaces. "
    "Source family: Parts Registry saved rows, Local Design Asset Catalog bundled seed records, "
    "and Plant Promoter Catalog profile rows. Plant expression construct context, record scope, "
    "and row granularity stay separate."
)

LOCAL_DESIGN_ASSET_CATALOG_INTRO_COPY = (
    "Source family: Local Design Asset Catalog. Record scope: bundled seed/catalog records. "
    "Row granularity: asset records, filtered table rows, review rows, and computed readback rows."
)

DATA_SURFACE_BOUNDARY_COPY = (
    "These library surfaces are documentation-only review aids and do not choose parts, assess biological fit, "
    "confirm records, generate protocols, optimize sequences, validate plant lines, predict yield, "
    "or provide wet-lab use guidance."
)

COMPONENT_OVERVIEW_COPY = (
    "Browse component records, source/provenance status, and manual follow-up for plant expression "
    "construct preparation."
)

PLANT_MVP_CONTEXT_TITLE = "Plant component/source/provenance review"

PLANT_MVP_CONTEXT_VALUE = "Plant recombinant protein / molecular farming"

PLANT_MVP_CONTEXT_COPY = (
    "Documentation-only boundary: source/provenance review and manual follow-up only. It does not "
    "recommend components, certify construct readiness, generate protocols, optimize sequences, "
    "validate plant lines, or predict yield."
)

PLANT_COMPONENT_CATEGORY_DESCRIPTIONS = (
    ("Plant promoter context", "promoter source/provenance and expression context notes for review"),
    ("Terminator context", "recorded terminator or polyA context for cassette documentation"),
    ("Signal peptide", "recorded secretion-leader or signal-peptide context"),
    ("Transit peptide", "recorded organelle transit-peptide context"),
    ("Subcellular targeting", "recorded compartment or targeting context"),
    ("Selectable marker / reporter", "marker and reporter documentation context"),
    ("Vector / backbone context", "vector or backbone source/provenance context"),
    ("Plant species / host context", "host species or plant source context recorded for review"),
    ("Tissue / organ / expression compartment", "tissue, organ, compartment, or expression-location context"),
    ("Expression mode", "recorded expression-mode context for documentation review"),
    ("Source / provenance", "source identity, citation, file, vendor, database, or lab-note context"),
    ("Manual follow-up", "missing or ambiguous documentation items for human review"),
)

PLANT_SOURCE_PROVENANCE_DETAIL_COPY = (
    "Use these rows to compare recorded source identity, provenance notes, review status, and missing "
    "documentation fields across existing component records. The software reads back recorded context; "
    "it does not verify biological suitability."
)

MANUAL_FOLLOW_UP_GUIDANCE_COPY = (
    "Manual follow-up means a person should inspect missing or ambiguous source, host, compartment, "
    "expression-mode, marker, backbone, or review-status notes before citing a record in documentation."
)

ADVANCED_COMPONENT_EVIDENCE_COPY = (
    "Advanced readback repeats table fields for narrow screens and review notes. It is supporting "
    "evidence context, not a component decision surface."
)

CORE_BROWSING_COPY = (
    "Core browsing stays visible. Auxiliary review, readback, export, and write tools are grouped below in collapsed sections."
)

REVIEW_FOLLOWUP_COPY = (
    "Source/provenance follow-up, manual review rows, and readback helpers stay together as auxiliary review material."
)

DOCUMENTATION_PREVIEW_COPY = (
    "Read-only documentation preview material. Not database export and not package schema export."
)

ADMIN_DIAGNOSTIC_COPY = (
    "Admin and diagnostic tools are collapsed here so normal browsing stays first."
)

PROMOTER_ASSET_ENTRY_COPY = (
    "Source family: Plant Promoter Catalog. Record scope: promoter profile rows. "
    "Row granularity: profile records, tissue evidence rows, motif rows, and review rows."
)

PROMOTER_ASSET_DETAIL_COPY = (
    "The Plant Promoter Catalog detail surface is plant promoter expression documentation and provenance "
    "context, not a promoter choice engine."
)

PROMOTER_ASSET_BOUNDARY_COPY = (
    "Promoter asset readback is documentation-only. It is not a biological recommendation, "
    "not compatibility proof, not a validation claim, not a behavior forecast, and not wet-lab use guidance."
)

GENERIC_ASSET_READBACK_COPY = (
    "Generic Component Library readback summarizes Local Design Asset Catalog records as computed readback rows. "
    "It preserves source/provenance identity and does not create a universal asset database model."
)

CONTRACT_CROSSWALK_READBACK_COPY = (
    "Contract crosswalk readback reuses existing Component Library records to show which documentation fields are recorded, "
    "missing, deferred, or out of scope. It is read-only review context and does not create or persist component records."
)

SELECTED_ASSET_DETAIL_COPY = (
    "Selected asset readback details are documentation-only source/provenance review context for the selected row. "
    "They are not experimental validation or biological approval."
)

SLOT_FIRST_BROWSE_COPY = (
    "Slot-first browse helps first-time users inspect existing Component Library records by plant expression "
    "construct review category. It shows source/provenance status and manual follow-up without choosing a component."
)

SLOT_FIRST_GLOSSARY_BOUNDARY_COPY = (
    "This section helps you review records and missing source information. "
    "It does not select components or validate the design."
)

SLOT_FIRST_GLOSSARY_TERMS = (
    (
        "Expression vector slot",
        "a place in the planned expression vector record, such as plant promoter context, insert, targeting context, marker, or backbone.",
    ),
    (
        "Component record",
        "a saved note about a biological part or vector-related item.",
    ),
    (
        "Source/provenance",
        "where the component information came from, such as a paper, database, vendor, sequence file, or lab note.",
    ),
    (
        "Manual follow-up",
        "something a person still needs to check or fill in before review.",
    ),
    (
        "CDS / Insert",
        "the coding sequence or DNA insert being documented for expression.",
    ),
    (
        "Vector / Backbone",
        "the plasmid or vector framework being documented.",
    ),
    (
        "Plant species / host context",
        "the plant host, source species, tissue, organ, or expression compartment recorded for review.",
    ),
    (
        "Expression mode",
        "the recorded expression-mode context, such as transient or stable expression, when present in documentation.",
    ),
    (
        "Terminator / PolyA",
        "an ending/control element recorded for the expression cassette.",
    ),
)

SLOT_COMPACT_DETAIL_COPY = (
    "Compact readback repeats the table's key review fields for narrow screens: slot, record names, "
    "source/provenance status, and manual follow-up. It is read-only review context, not component selection."
)


def _scope_caption(source_family: str, record_scope: str, row_granularity: str) -> str:
    return (
        f"Source family: {source_family}; "
        f"Record scope: {record_scope}; "
        f"Row granularity: {row_granularity}"
    )

_DISPLAY_COLS = [
    "Name", "Type", "Organism", "Function Summary", "Length (bp)",
    "GC Content (%)", "Description", "Sequence Preview", "Created At",
]

_DETAIL_FIELDS = [
    ("Name", "Name"),
    ("Part Type", "Type"),
    ("Host", "Organism"),
    ("Function Summary", "Function Summary"),
    ("Common Usage", "Common Usage"),
    ("Key Features", "Key Features"),
    ("Documented Pairing Context", "Documented Pairing Context"),
    ("Source Type", "Source Type"),
    ("Notes", "Notes"),
]


_REGULATORY_STEP2_TYPES = {"Promoter", "RBS", "Terminator"}


def _documentation_detail_fallback(value: object, *, placeholder: str = "Not recorded in this documentation view") -> str:
    text = str(value or "").strip()
    return text or placeholder


def _clean_sequence(raw: str) -> str:
    return re.sub(r"[\s0-9]", "", raw).upper()


def _validate_sequence(seq: str) -> tuple[bool, str]:
    if not seq:
        return False, "Sequence cannot be empty."
    invalid = sorted(set(seq) - frozenset("ATCGN"))
    if invalid:
        return False, f"Invalid characters found: {', '.join(invalid)}. Only A, T, C, G, and N are allowed."
    return True, ""


def _compute_gc(seq: str) -> float:
    if not seq:
        return 0.0
    return (seq.count("G") + seq.count("C")) / len(seq) * 100


def _looks_like_sequence(text: str) -> bool:
    cleaned = re.sub(r"\s", "", text).upper()
    return len(cleaned) >= 4 and all(c in "ATCGN" for c in cleaned)


class _ParsedRecord:
    __slots__ = ("index", "name", "description", "sequence", "part_type", "length_bp", "gc_content", "seq_error", "is_duplicate")

    def __init__(self, index, name, description, sequence, part_type):
        self.index = index
        self.name = name
        self.description = description
        self.sequence = sequence
        self.part_type = part_type
        self.length_bp = len(sequence)
        self.gc_content = _compute_gc(sequence)
        self.seq_error = ""
        self.is_duplicate = False


def _parse_fasta_bytes(raw_bytes: bytes, part_type: str) -> tuple[list, list]:
    from Bio import SeqIO

    parse_errors: list[str] = []
    try:
        file_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            file_text = raw_bytes.decode("latin-1")
            parse_errors.append("File decoded as Latin-1 instead of UTF-8. Non-ASCII characters in headers may display incorrectly.")
        except Exception:
            return [], ["File encoding error: unable to decode the uploaded file."]

    handle = io.StringIO(file_text)
    try:
        bio_records = list(SeqIO.parse(handle, "fasta"))
    except Exception as exc:
        return [], [f"BioPython parsing error: {exc}"]
    if not bio_records:
        return [], ["No FASTA records found. The file may be empty or not in FASTA format."]

    records: list[_ParsedRecord] = []
    for idx, bio_rec in enumerate(bio_records, start=1):
        name = bio_rec.id or f"unnamed_{idx}"
        raw_desc = bio_rec.description
        if raw_desc.startswith(name):
            raw_desc = raw_desc[len(name):].strip()
        raw_seq = str(bio_rec.seq)
        if not raw_seq:
            parse_errors.append(f"Record {idx} \"{name}\": sequence is empty and was skipped.")
            continue
        seq_clean = _clean_sequence(raw_seq)
        rec = _ParsedRecord(idx, name, raw_desc, seq_clean, part_type)
        ok, err = _validate_sequence(seq_clean)
        if not ok:
            rec.seq_error = f"Record {idx} \"{name}\": {err}"
        records.append(rec)
    return records, parse_errors


def _load_parts(filter_type: str | None = None) -> pd.DataFrame:
    return get_all_parts_cached(filter_type=filter_type)


def _apply_filters(df, keyword, type_filter, full_sequence_search=False):
    if type_filter:
        df = df[df["Type"].isin(type_filter)]
    kw = keyword.strip()
    if not kw:
        return df
    if _looks_like_sequence(kw):
        sequence_col = "Sequence" if full_sequence_search else "Sequence Preview"
        mask = df[sequence_col].str.upper().str.contains(kw.upper(), na=False, regex=False)
        return df[mask]
    kw_low = kw.lower()
    mask = (
        df["Name"].str.lower().str.contains(kw_low, na=False, regex=False)
        | df["Description"].str.lower().str.contains(kw_low, na=False, regex=False)
        | df["Function Summary"].str.lower().str.contains(kw_low, na=False, regex=False)
        | df["Type"].str.lower().str.contains(kw_low, na=False, regex=False)
    )
    return df[mask]


def _df_to_csv(df):
    return df[_DISPLAY_COLS].to_csv(index=False).encode("utf-8-sig")


def _df_to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df[_DISPLAY_COLS].to_excel(w, index=False, sheet_name="Parts")
    return buf.getvalue()


def _paginate_dataframe(df: pd.DataFrame, page: int, page_size: int) -> tuple[pd.DataFrame, int, int, int]:
    """Return a page slice plus normalized paging metadata."""
    total_rows = len(df)
    normalized_page_size = max(int(page_size), 1)
    total_pages = max((total_rows - 1) // normalized_page_size + 1, 1)
    normalized_page = min(max(int(page), 1), total_pages)
    start_idx = (normalized_page - 1) * normalized_page_size
    end_idx = start_idx + normalized_page_size
    return df.iloc[start_idx:end_idx], normalized_page, total_pages, total_rows


def _paging_summary(page: int, page_size: int, total_rows: int) -> str:
    """Build a compact summary for the current page window."""
    if total_rows == 0:
        return _t("data.paging.empty")
    start_row = (page - 1) * page_size + 1
    end_row = min(start_row + page_size - 1, total_rows)
    return _t("data.paging.summary", start=start_row, end=end_row, total=total_rows)


def _build_browsing_scope(
    keyword: str,
    type_filter: list[str],
    full_sequence_search: bool,
    page_size: int,
) -> tuple[str, tuple[str, ...], bool, int]:
    """Normalize the active registry browsing scope for pagination state."""
    return (
        keyword.strip(),
        tuple(sorted(type_filter)),
        bool(full_sequence_search),
        int(page_size),
    )


def _resolve_page_for_scope(
    current_page: int,
    previous_scope: tuple[str, tuple[str, ...], bool, int] | None,
    current_scope: tuple[str, tuple[str, ...], bool, int],
) -> int:
    """Reset to page 1 whenever the effective browsing scope changes."""
    if previous_scope != current_scope:
        return 1
    return max(int(current_page), 1)


def _did_registry_view_change(
    previous_scope: tuple[str, tuple[str, ...], bool, int] | None,
    current_scope: tuple[str, tuple[str, ...], bool, int],
    previous_page: int,
    current_page: int,
) -> bool:
    """Detect when filters or pagination move the table to a new visible page."""
    return previous_scope != current_scope or int(previous_page) != int(current_page)



def _resolve_selected_row_in_scope(
    paged_df: pd.DataFrame,
    selected_part_id: int | None,
) -> pd.Series | None:
    """Keep selection only while the selected part remains in the current page scope."""
    if selected_part_id is None:
        return None

    page_matches = paged_df[paged_df["ID"] == selected_part_id]
    if not page_matches.empty:
        return page_matches.iloc[0]

    return None



def _resolve_selected_part_id_for_visible_page(
    paged_df: pd.DataFrame,
    selected_part_id: int | None,
    selected_rows: list[int],
    apply_event_selection: bool,
) -> int | None:
    """Keep or update the selected part id without rebinding stale row indices."""
    if apply_event_selection:
        if not selected_rows:
            return None

        selected_index = int(selected_rows[0])
        if 0 <= selected_index < len(paged_df):
            return int(paged_df.iloc[selected_index]["ID"])
        return None

    scoped_row = _resolve_selected_row_in_scope(paged_df, selected_part_id)
    if scoped_row is None:
        return None
    return int(scoped_row["ID"])


def _build_step2_candidate_payload(selected_row) -> dict:
    """Build the transient Step 2 candidate payload from a registry row."""
    part_id = selected_row.get("ID", selected_row.get("id", ""))
    part_type = normalize_part_type(str(selected_row.get("Type", selected_row.get("part_type", ""))))
    sequence = _clean_sequence(str(selected_row.get("Sequence", selected_row.get("sequence", ""))))
    organism = str(selected_row.get("Organism", selected_row.get("organism", ""))).strip()
    notes = str(selected_row.get("Notes", selected_row.get("notes", ""))).strip()
    payload = {
        "source": "parts_registry",
        "origin_page": "Parts Registry",
        "part_id": part_id,
        "registry_id": part_id,
        "part_type": part_type,
        "canonical_type": part_type,
        "name": str(selected_row.get("Name", selected_row.get("name", ""))).strip(),
        "sequence": sequence,
        "host_context": organism,
        "organism": organism,
        "notes": notes,
        "warnings": [notes] if notes else [],
    }
    for payload_key, row_key in (
        ("description", "Description"),
        ("source_type", "Source Type"),
        ("function_summary", "Function Summary"),
        ("common_usage", "Common Usage"),
        ("key_features", "Key Features"),
        ("recommended_pairing", "Documented Pairing Context"),
        ("created_at", "Created At"),
    ):
        value = selected_row.get(row_key, "")
        if value not in (None, ""):
            payload[payload_key] = str(value).strip()
    try:
        payload["length_bp"] = int(selected_row.get("Length (bp)", len(sequence)))
    except Exception:
        payload["length_bp"] = len(sequence)
    try:
        payload["gc_percent"] = float(selected_row.get("GC Content (%)", _compute_gc(sequence)))
    except Exception:
        payload["gc_percent"] = _compute_gc(sequence)
    return payload


def _is_step2_candidate_type(part_type: str) -> bool:
    return normalize_part_type(part_type) in _REGULATORY_STEP2_TYPES


def _render_part_detail(selected_row, tab_key):
    st.divider()
    st.caption("Documentation Details")
    if selected_row is None:
        st.info("Select a record in the table to view documentation details, sequence preview, and available next actions.")
        return

    for label, column in _DETAIL_FIELDS:
        value = selected_row.get(column, "")
        text = str(value).strip() if value is not None else ""
        st.markdown(f"**{label}:** {text if text else '—'}")

    st.text_area(
        "Sequence",
        value=str(selected_row.get("Sequence", "")).strip(),
        height=140,
        disabled=True,
        key=f"sequence_detail_{tab_key}",
    )

    # ---- Wizard Step 2 candidate action --------------------------------
    st.caption("This sends a candidate only. It will not confirm Step 2 or modify saved design fields.")
    normalized_type = normalize_part_type(str(selected_row.get("Type", "")))
    can_send_step2 = _is_step2_candidate_type(normalized_type)
    if st.button(
        "Send to Wizard Step 2 Candidate",
        use_container_width=True,
        key=f"btn_send_step2_candidate_{tab_key}",
        disabled=not can_send_step2,
        help="Only promoter, RBS/Kozak, and terminator parts can be sent to Wizard Step 2." if not can_send_step2 else "Send this part as a transient Step 2 candidate.",
    ):
        from core.context_bridge import send_parts_step2_candidate

        payload = _build_step2_candidate_payload(selected_row)
        send_parts_step2_candidate(payload)
        st.success("Candidate sent to Expression Wizard Step 2.")

    # ---- Edit / Delete actions -----------------------------------------
    st.divider()
    act_edit, act_del = st.columns([1, 1])
    with act_edit:
        if st.button("Save Documentation Record", use_container_width=True, key=f"btn_edit_{tab_key}"):
            _edit_dialog(selected_row)
    with act_del:
        if st.button("Remove Record", use_container_width=True, key=f"btn_del_{tab_key}", type="secondary"):
            st.session_state[f"confirm_delete_{tab_key}"] = True

    if st.session_state.get(f"confirm_delete_{tab_key}", False):
        part_name = str(selected_row.get("Name", "")).strip() or "Unknown part"
        part_type = str(selected_row.get("Type", "")).strip()
        part_id = int(selected_row["ID"])
        type_text = f" ({part_type})" if part_type else ""
        st.warning(
            f"Delete this local registry record permanently? **{part_name}**{type_text}. "
            "This cannot be undone and may affect workflows that use registry parts."
        )
        cc, cv = st.columns([1, 1])
        with cc:
            if st.button("Cancel", key=f"del_cancel_{tab_key}", use_container_width=True):
                st.session_state[f"confirm_delete_{tab_key}"] = False
                st.rerun()
        with cv:
            if st.button("Confirm Delete", key=f"del_confirm_{tab_key}", type="primary", use_container_width=True):
                success, msg = delete_part(part_id)
                st.session_state[f"confirm_delete_{tab_key}"] = False
                if success:
                    st.cache_data.clear()
                    st.toast(f"Part '{part_name}' has been deleted.", icon="🗑️")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {msg}")


def _render_export_controls(df: pd.DataFrame, key_suffix: str) -> None:
    """Render exports for the currently filtered registry table."""
    with st.expander("Documentation preview export actions", expanded=False):
        st.caption(DOCUMENTATION_PREVIEW_COPY)
        st.download_button(
            "Export Documentation Preview CSV",
            data=_df_to_csv(df),
            file_name=f"parts_registry_{key_suffix}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"export_csv_{key_suffix}",
        )
        st.download_button(
            "Export Documentation Preview Excel",
            data=_get_excel_export_data(df),
            file_name=f"parts_registry_{key_suffix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"export_excel_{key_suffix}",
        )


def _excel_export_available() -> bool:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return False
    return True


def _get_excel_export_data(df: pd.DataFrame) -> bytes:
    if not _excel_export_available():
        st.info("Excel export requires openpyxl. CSV export is still available.")
        return b""
    return _df_to_excel(df)

def _render_part_table(filter_type=None, tab_key="all"):
    df_raw = _load_parts(filter_type=filter_type)
    sc, tc = st.columns([3, 2])
    with sc:
        keyword = st.text_input(_t("data.search"), placeholder=_t("data.search_placeholder"), key=f"search_{tab_key}", label_visibility="collapsed")
    with tc:
        type_filter = st.multiselect(_t("data.type"), list(ALLOWED_TYPES), default=[], key=f"tf_{tab_key}", label_visibility="collapsed", placeholder=_t("data.type_placeholder"), format_func=_part_type_label) if filter_type is None else []

    full_sequence_search = st.checkbox(
        _t("data.search_full_sequence"),
        value=False,
        key=f"full_seq_search_{tab_key}",
        help=_t("data.search_full_sequence_help"),
    )

    df = _apply_filters(df_raw, keyword, type_filter, full_sequence_search=full_sequence_search)
    if keyword.strip() and _looks_like_sequence(keyword):
        search_scope = "full sequence" if full_sequence_search else "45 bp preview"
        st.caption(f"Sequence fragment search: '{keyword.strip().upper()}' (matched in {search_scope}).")

    _sel_id_key = f"selected_part_id_{tab_key}"
    if df.empty:
        st.session_state.pop(_sel_id_key, None)
        st.info("No reference records found. Adjust the search/filter controls, switch tabs, or add a reference record to create a documentation-only entry.")
        return

    page_size_options = [10, 25, 50, 100]
    page_size = st.selectbox(
        _t("data.rows_per_view"),
        options=page_size_options,
        index=page_size_options.index(25),
        key=f"page_size_{tab_key}",
        help=_t("data.rows_per_view_help"),
    )
    page_key = f"page_{tab_key}"
    scope_key = f"page_scope_{tab_key}"
    current_scope = _build_browsing_scope(keyword, type_filter, full_sequence_search, page_size)
    previous_scope = st.session_state.get(scope_key)
    previous_page = st.session_state.get(page_key, 1)
    current_page = _resolve_page_for_scope(
        previous_page,
        previous_scope,
        current_scope,
    )
    paged_df, current_page, total_pages, total_rows = _paginate_dataframe(df, current_page, page_size)
    view_changed = _did_registry_view_change(previous_scope, current_scope, previous_page, current_page)
    st.session_state[page_key] = current_page
    st.session_state[scope_key] = current_scope

    controls_col, nav_col, export_col = st.columns([3, 3, 2])
    with controls_col:
        st.caption(_paging_summary(current_page, page_size, total_rows))
    with nav_col:
        prev_col, page_col, next_col = st.columns([1, 2, 1])
        with prev_col:
            if st.button("←", key=f"prev_page_{tab_key}", use_container_width=True, disabled=current_page <= 1):
                st.session_state[page_key] = current_page - 1
                st.rerun()
        with page_col:
            selected_page = st.selectbox(
                _t("data.page"),
                options=list(range(1, total_pages + 1)),
                index=current_page - 1,
                key=f"page_select_{tab_key}",
                label_visibility="collapsed",
            )
            if selected_page != current_page:
                st.session_state[page_key] = selected_page
                st.rerun()
        with next_col:
            if st.button("→", key=f"next_page_{tab_key}", use_container_width=True, disabled=current_page >= total_pages):
                st.session_state[page_key] = current_page + 1
                st.rerun()
    with export_col:
        _render_export_controls(df, key_suffix=tab_key)

    event = st.dataframe(
        paged_df[_DISPLAY_COLS],
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"parts_table_{tab_key}",
        column_config={
            "Name":             st.column_config.TextColumn("Name",        width="medium"),
            "Type":             st.column_config.TextColumn("Type",        width="small"),
            "Organism":         st.column_config.TextColumn("Host",        width="medium"),
            "Function Summary": st.column_config.TextColumn("Function Summary",    width="large",  help="Structured basic description of the part."),
            "Length (bp)":      st.column_config.NumberColumn("Length (bp)", width="small",  format="%d"),
            "GC Content (%)":   st.column_config.NumberColumn("GC Content (%)", width="small", format="%.2f"),
            "Description":      st.column_config.TextColumn("Description",        width="medium"),
            "Sequence Preview": st.column_config.TextColumn("Sequence Preview",    width="large",  help="First 45 bp. Click a cell to copy."),
            "Created At":       st.column_config.TextColumn("Created At",    width="medium"),
        },
    )
    selected_row = None
    event_selection = []
    if event and hasattr(event, "selection"):
        event_selection = event.selection.get("rows", [])

    selected_part_id = _resolve_selected_part_id_for_visible_page(
        paged_df=paged_df,
        selected_part_id=st.session_state.get(_sel_id_key),
        selected_rows=event_selection,
        apply_event_selection=bool(event_selection) and not view_changed,
    )

    if selected_part_id is None:
        st.session_state.pop(_sel_id_key, None)
    else:
        st.session_state[_sel_id_key] = selected_part_id
        selected_row = _resolve_selected_row_in_scope(
            paged_df=paged_df,
            selected_part_id=selected_part_id,
        )
    _render_part_detail(selected_row, tab_key)


def _submit_part(name, part_type, raw_seq, description, organism="Universal"):
    if not name.strip():
        st.error("Part name is required.")
        return
    seq_clean = _clean_sequence(raw_seq)
    ok, err = _validate_sequence(seq_clean)
    if not ok:
        st.error(f"Sequence validation failed: {err}")
        return
    success, msg = add_part({
        "name": name.strip(),
        "part_type": part_type,
        "organism": organism,
        "sequence": seq_clean,
        "description": description.strip(),
    })
    if success:
        st.cache_data.clear()
        st.toast(f"Part '{msg}' has been registered.", icon="✅")
        st.rerun()
    else:
        st.error(f"Registration failed: {msg}")


def _manual_name_duplicate(name: str, existing_names: frozenset[str] | None = None) -> str | None:
    """Return the matched existing part name for manual single-part entry."""
    normalized_name = name.strip()
    if not normalized_name:
        return None

    existing = existing_names if existing_names is not None else get_existing_names()
    if normalized_name in existing:
        return normalized_name
    return None


@st.dialog("Edit Part", width="large")
def _edit_dialog(selected_row) -> None:
    """Pre-populated edit form for an existing part row."""
    part_id = int(selected_row["ID"])
    st.caption(f"Editing part ID {part_id}. Fields marked with * are required.")
    st.info("Editing updates this local registry record and may affect workflows that reuse it.")

    e_name = st.text_input("Part Name *", value=str(selected_row.get("Name", "")), key="edit_name")
    e_type = st.selectbox(
        "Part Type *",
        ALLOWED_TYPES,
        index=ALLOWED_TYPES.index(selected_row["Type"]) if selected_row["Type"] in ALLOWED_TYPES else 0,
        key="edit_type",
    )
    org_options = ["Universal"] + list(ALLOWED_ORGANISMS)
    current_org = str(selected_row.get("Organism", "Universal"))
    e_org = st.selectbox(
        "Host *",
        org_options,
        index=org_options.index(current_org) if current_org in org_options else 0,
        key="edit_org",
    )
    e_desc = st.text_input("Description", value=str(selected_row.get("Description", "")), key="edit_desc")
    e_seq = st.text_area(
        "Sequence *",
        value=str(selected_row.get("Sequence", "")),
        height=100,
        key="edit_seq",
    )
    sc = _clean_sequence(e_seq)
    sok, serr = _validate_sequence(sc) if sc else (False, "")
    if sc:
        if sok:
            c1, c2 = st.columns(2)
            c1.metric("Length", f"{len(sc):,} bp")
            c2.metric("GC Content", f"{_compute_gc(sc):.1f}%")
        else:
            st.error(serr)

    with st.expander("Metadata Fields (Optional)", expanded=False):
        e_source = st.text_input("Source Type", value=str(selected_row.get("Source Type", "")), key="edit_source")
        e_func = st.text_area("Function Summary", value=str(selected_row.get("Function Summary", "")), height=68, key="edit_func")
        e_usage = st.text_area("Common Usage", value=str(selected_row.get("Common Usage", "")), height=68, key="edit_usage")
        e_feat = st.text_area("Key Features", value=str(selected_row.get("Key Features", "")), height=68, key="edit_feat")
        e_pair = st.text_area(
            "Documented Pairing Context",
            value=str(
                selected_row.get(
                    "Documented Pairing Context",
                    selected_row.get("Review Pairing Notes", selected_row.get("Recommended Pairing", "")),
                )
            ),
            height=68,
            key="edit_pair",
        )
        e_notes = st.text_area("Notes", value=str(selected_row.get("Notes", "")), height=68, key="edit_notes")

    st.divider()
    ca, cs = st.columns([1, 2])
    with ca:
        if st.button("Cancel", use_container_width=True, key="edit_cancel"):
            st.rerun()
    with cs:
        if st.button(
            "Save Changes",
            type="primary",
            use_container_width=True,
            disabled=not (sc and sok and e_name.strip()),
            key="edit_save",
        ):
            success, msg = update_part(
                part_id,
                {
                    "name": e_name.strip(),
                    "part_type": e_type,
                    "organism": e_org,
                    "sequence": e_seq,
                    "description": e_desc.strip(),
                    "source_type": e_source.strip(),
                    "function_summary": e_func.strip(),
                    "common_usage": e_usage.strip(),
                    "key_features": e_feat.strip(),
                    "recommended_pairing": e_pair.strip(),
                    "notes": e_notes.strip(),
                },
            )
            if success:
                st.cache_data.clear()
                st.toast(f"Part '{msg}' has been updated.", icon="✅")
                st.rerun()
            else:
                st.error(f"Update failed: {msg}")


@st.dialog("Add Reference Record", width="large")
def _register_dialog():
    tab_manual, tab_fasta = st.tabs([_t("data.tab.manual"), _t("data.tab.fasta_import")])
    st.info(_REGISTRY_MUTATION_NOTICE)

    with tab_manual:
        st.caption("Fields marked with * are required. Sequences are automatically cleaned by removing whitespace/numbers and converting to uppercase.")
        st.info("Adding a part creates a local registry record.")
        pname = st.text_input("Part Name *", placeholder="Example: CaMV35S Promoter", key="dlg_name")
        ptype = st.selectbox(_t("data.field.part_type_required"), ALLOWED_TYPES, key="dlg_type", format_func=_part_type_label)
        porg = st.selectbox("Host *", ["Universal"] + list(ALLOWED_ORGANISMS), key="dlg_org")
        pdesc = st.text_input("Description", placeholder="Optional", key="dlg_desc")
        pseq = st.text_area("Sequence *", placeholder="Paste DNA sequence...", height=100, key="dlg_seq")
        existing_names = get_existing_names()
        duplicate_name = _manual_name_duplicate(pname, existing_names)
        if duplicate_name:
            st.warning(
                f"A part named '{duplicate_name}' already exists in the registry. "
                "Submitting will still use the current write path and may fail if the name is unchanged."
            )
        sc = _clean_sequence(pseq)
        sok, serr = _validate_sequence(sc) if sc else (False, "")
        if sc:
            if sok:
                c1, c2 = st.columns(2)
                c1.metric("Length", f"{len(sc):,} bp")
                c2.metric("GC Content", f"{_compute_gc(sc):.1f}%")
            else:
                st.error(serr)
        st.divider()
        ca, cs = st.columns([1, 2])
        with ca:
            if st.button("Cancel", use_container_width=True, key="dlg_cancel"):
                st.rerun()
        with cs:
            if st.button("Submit to Registry", type="primary", use_container_width=True, disabled=not (sc and sok and pname.strip()), key="dlg_submit"):
                _submit_part(pname, ptype, pseq, pdesc, porg)

    with tab_fasta:
        st.caption("Upload a .fasta/.fa file, assign one part type to all records, and preview before submission.")
        ff = st.file_uploader("FASTA File *", type=["fasta", "fa", "txt"], key="dlg_fasta_file")
        bt = st.selectbox(_t("data.field.part_type_required"), ALLOWED_TYPES, key="dlg_batch_type", format_func=_part_type_label)
        bo = st.selectbox("Host *", ["Universal"] + list(ALLOWED_ORGANISMS), key="dlg_batch_org")
        ow = st.checkbox(
            "Overwrite existing parts with the same name",
            value=False,
            key="dlg_overwrite",
            help=(
                "Overwrite replaces matching local registry records by name. Use only when you "
                "intentionally want to replace existing local entries."
            ),
        )
        st.warning(
            "Overwrite replaces matching local registry records by name. Use only when you "
            "intentionally want to replace existing local entries."
        )
        if ff is None:
            st.info("Upload a FASTA file to preview records.")
            return
        recs, perrs = _parse_fasta_bytes(ff.read(), bt)
        for pe in perrs:
            st.warning(pe)
        if not recs:
            st.error("No valid records were parsed.")
            return
        existing = get_existing_names()
        for r in recs:
            r.is_duplicate = r.name in existing
        rows = []
        for r in recs:
            if r.seq_error:
                status = "Error: " + r.seq_error.split(":", 2)[-1].strip()
            elif r.is_duplicate:
                status = "Duplicate" + (" - overwrite" if ow else " - skip")
            else:
                status = "Available for import preview"
            rows.append({"#": r.index, "Name": r.name, "Description": r.description[:38] + "..." if len(r.description) > 38 else r.description, "bp": r.length_bp, "GC": f"{r.gc_content:.1f}", "Status": status})
        pdf = pd.DataFrame(rows)
        n_ok = sum(1 for r in recs if not r.seq_error and (not r.is_duplicate or ow))
        n_dup = sum(1 for r in recs if r.is_duplicate)
        n_err = sum(1 for r in recs if r.seq_error)
        st.markdown(f"Parsed **{len(recs)}** records — **{n_ok}** to write, **{n_dup}** duplicates, **{n_err}** invalid.")

        def _cs(v):
            if v.startswith("Error"):
                return "color:#dc2626;font-weight:600"
            if v.startswith("Duplicate"):
                return "color:#d97706;font-weight:600"
            return "color:#16a34a"

        st.dataframe(pdf.style.map(_cs, subset=["Status"]), use_container_width=True, hide_index=True)
        if n_ok == 0:
            st.warning("No records are available for import.")
            return
        st.divider()
        if st.button(f"Submit {n_ok} Records", type="primary", use_container_width=True, key="dlg_commit"):
            bar = st.progress(0, text="Writing...")
            payloads = [{"name": r.name, "part_type": r.part_type, "organism": bo, "sequence": r.sequence, "description": r.description} for r in recs if not r.seq_error]
            for p in range(0, 80, 20):
                bar.progress(p, text="Writing...")
            ins, skp, errs = add_parts_batch(payloads, overwrite=ow)
            bar.progress(100, text="Complete.")
            for e in errs:
                st.error(e)
            if ins > 0:
                st.cache_data.clear()
                st.success(f"Imported **{ins}** parts. {skp} skipped.")
                st.rerun()
            else:
                st.warning(f"No parts were written. Skipped {skp}; errors {len(errs)}.")


def _render_documentation_artifact_library() -> None:
    st.subheader("Saved Documentation Artifacts")
    st.info(ARTIFACT_LIBRARY_SAFETY_COPY)
    st.caption(ARTIFACT_LIBRARY_WORKFLOW_COPY)
    artifacts = list_tool_artifacts()
    search_query = st.text_input(
        "Search saved documentation artifacts",
        key="tool_artifact_library_search",
        placeholder="Search by title, source tool, type, summary, or notes",
    )
    type_options = sorted({str(item.get("artifact_type") or "") for item in artifacts if item.get("artifact_type")})
    selected_type = st.selectbox(
        "Filter by artifact type",
        options=[""] + type_options,
        format_func=lambda value: "All artifact types" if not value else value,
        key="tool_artifact_library_type_filter",
    )
    project_options = sorted({str(item.get("project_id")) for item in artifacts if item.get("project_id") not in (None, "")})
    selected_project = st.selectbox(
        "Filter by linked project",
        options=[""] + project_options,
        format_func=lambda value: "All linked projects" if not value else f"Project {value}",
        key="tool_artifact_library_project_filter",
    )
    show_unlinked = st.checkbox(
        "Show unlinked documentation artifacts",
        value=False,
        key="tool_artifact_library_show_unlinked",
    )
    filtered = filter_documentation_artifacts(
        artifacts,
        search_query=search_query,
        artifact_type=selected_type or None,
        linked_project=selected_project or None,
        show_unlinked=show_unlinked,
    )
    if not artifacts:
        st.info(artifact_library_empty_state(linked_project_scope=False))
        return
    if not filtered:
        st.info("No saved documentation artifacts match the current search or filter. Documentation artifacts are optional review records for traceability.")
        return
    rows = [
        {
            "created_at": artifact.get("created_at", ""),
            "record type": artifact.get("artifact_type", ""),
            "title": artifact.get("title", ""),
            "created from": artifact.get("source_module", ""),
            "linked project": artifact.get("project_id") or "Unlinked",
            "summary/preview": artifact.get("summary", ""),
        }
        for artifact in filtered
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    selected_id = st.selectbox(
        "Artifact detail preview",
        options=[artifact.get("artifact_id") for artifact in filtered],
        format_func=lambda artifact_id: next((str(item.get("title") or artifact_id) for item in filtered if item.get("artifact_id") == artifact_id), str(artifact_id)),
        key="tool_artifact_library_detail_select",
    )
    selected = next((item for item in filtered if item.get("artifact_id") == selected_id), None)
    if not selected:
        return
    labels = artifact_detail_preview_labels()
    st.markdown(f"**{labels['heading']}**")
    st.caption(ARTIFACT_DETAIL_PREVIEW_COPY)
    st.markdown(f"**{labels['artifact_type']}:** {selected.get('artifact_type', '—')}")
    st.markdown(f"**{labels['source_tool']}:** {selected.get('source_module', '—')}")
    st.markdown(f"**{labels['linked_project']}:** {selected.get('project_id') or 'Unlinked'}")
    st.markdown(f"**{labels['created_timestamp']}:** {selected.get('created_at', '—')}")
    st.markdown(f"**{labels['summary_preview']}:** {selected.get('summary', '—')}")
    for label, value in readable_payload_summary(selected.get("payload_json")):
        st.markdown(f"**{label}:** {value}")
    st.caption(labels["record_boundary"])
    st.caption(str(selected.get("boundary_label") or ""))
    with st.expander(labels["raw_payload"], expanded=False):
        raw_text, truncated = raw_payload_preview(selected.get("payload_json"), max_chars=2000)
        st.code(raw_text + ("\n... truncated for display" if truncated else ""), language="json")
    if st.button("Remove saved documentation artifact", key="tool_artifact_library_delete_request", type="secondary"):
        st.session_state["tool_artifact_library_confirm_delete"] = selected_id
    if st.session_state.get("tool_artifact_library_confirm_delete") == selected_id:
        st.warning(ARTIFACT_DELETE_CONFIRMATION_COPY)
        cancel_col, confirm_col = st.columns([1, 1])
        with cancel_col:
            if st.button("Cancel artifact removal", key="tool_artifact_library_delete_cancel", use_container_width=True):
                st.session_state.pop("tool_artifact_library_confirm_delete", None)
                st.rerun()
        with confirm_col:
            if st.button("Confirm artifact removal", key="tool_artifact_library_delete_confirm", use_container_width=True):
                success, message = delete_tool_artifact(selected_id)
                st.session_state.pop("tool_artifact_library_confirm_delete", None)
                if success:
                    st.success(message)
                    st.rerun()
                st.error(message)


def _render_local_design_asset_catalog() -> None:
    st.subheader("Local Design Asset Catalog")
    render_help_text(LOCAL_DESIGN_ASSET_CATALOG_INTRO_COPY)
    st.caption(
        _scope_caption(
            "Local Design Asset Catalog",
            "bundled seed/catalog records",
            "asset records with filtered table rows, review rows, and readback rows",
        )
    )
    seed_catalog = load_local_design_asset_seed_catalog()
    records = seed_catalog["records"]
    if not records:
        st.info("No local design asset records are present.")
        return

    counts = summarize_local_design_asset_counts(records)
    review_counts = summarize_local_design_asset_review_status(records)
    inventory = summarize_local_design_asset_inventory(records)
    seed_metadata = seed_catalog["metadata"]

    filter_col, search_col = st.columns([1, 2])
    with filter_col:
        selected_asset_type = st.selectbox(
            "Filter by asset type",
            options=[""] + [asset_type for asset_type, count in counts.items() if count],
            format_func=lambda value: "All asset types" if not value else value,
            key="local_design_asset_type_filter",
        )
    with search_col:
        search_query = st.text_input(
            "Search local design assets",
            placeholder="Search by display name, alias, tag, or note",
            key="local_design_asset_search",
        )
    filtered = filter_local_design_assets_by_type(records, selected_asset_type or "") if selected_asset_type else list(records)
    filtered = search_local_design_assets(filtered, search_query)
    render_compact_summary_cards(
        [
            (
                "Bundled asset records",
                str(inventory["total_record_count"]),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "asset records"),
            ),
            (
                "Filtered table rows",
                str(len(filtered)),
                _scope_caption("Local Design Asset Catalog", "current filter matches", "filtered preview rows"),
            ),
            (
                "Asset type groups",
                str(sum(1 for value in counts.values() if value)),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "grouped asset families"),
            ),
            (
                "Source/provenance review rows",
                str(review_counts["source_review_needed"]),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "review rows"),
            ),
            (
                "Human review rows",
                str(review_counts["human_review_needed"]),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "review rows"),
            ),
        ]
    )
    st.caption(
        "Saved bundled asset records stay separate from filtered table rows. "
        "The table below is a filtered preview of current matches, while the selected detail panel is a single record."
    )
    st.caption(
        "Reference bridge: these catalog records can be reviewed here first, then cited later as linked catalog context "
        "inside Expression Wizard Step 6 or Pathway Workspace project documentation."
    )
    if seed_metadata.get("seed_name") or seed_metadata.get("seed_version"):
        st.caption(
            f"Seed metadata: {seed_metadata.get('seed_name', '').strip()} {seed_metadata.get('seed_version', '').strip()}".strip()
        )
    if seed_metadata.get("seed_scope"):
        st.caption(f"Seed scope: {seed_metadata['seed_scope']}")

    st.markdown("**Asset categories in this local catalog**")
    category_lines = [f"- **{asset_type}**: {count}" for asset_type, count in counts.items() if count]
    st.markdown("\n".join(category_lines) if category_lines else "- No asset categories available.")
    st.caption(
        "Records are documentation-only asset entries for review and traceability. "
        "Filtered table rows are not extra saved records."
    )
    if inventory["represented_source_contexts"]:
        st.caption(
            "Represented source contexts: "
            + ", ".join(inventory["represented_source_contexts"][:6])
            + (" ..." if len(inventory["represented_source_contexts"]) > 6 else "")
        )
    st.markdown("**Filtered table rows**")
    st.caption(f"Showing {len(filtered)} of {inventory['total_record_count']} bundled records.")
    if not filtered:
        st.info("No local design asset documentation records match the current search or filter. Adjust the controls to continue browsing the local catalog.")
        return

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "display_name": record.get("display_name", ""),
                    "asset_type": record.get("asset_type", ""),
                    "provenance_status": record.get("provenance_status", ""),
                    "review_status": record.get("review_status", ""),
                    "sequence_available": record.get("sequence_available", False),
                }
                for record in filtered
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    selected_label = st.selectbox(
        "Documentation-only candidate record for review",
        options=[record.get("asset_id") for record in filtered],
        format_func=lambda asset_id: next((str(item.get("display_name") or asset_id) for item in filtered if item.get("asset_id") == asset_id), str(asset_id)),
        key="local_design_asset_detail_select",
    )
    selected = next((record for record in filtered if record.get("asset_id") == selected_label), None)
    if not selected:
        return
    host_context = summarize_asset_host_chassis_context(selected)

    with st.expander("Selected asset documentation details", expanded=False):
        st.caption(SELECTED_ASSET_DETAIL_COPY)
        detail_left, detail_right = st.columns(2)
        with detail_left:
            st.markdown("**Identity**")
            st.markdown(f"- **display_name:** {_documentation_detail_fallback(selected.get('display_name'))}")
            st.markdown(f"- **asset_type:** {_documentation_detail_fallback(selected.get('asset_type'))}")
            st.markdown(
                f"- **aliases:** {_documentation_detail_fallback(', '.join(selected.get('aliases') or []))}"
            )
            st.markdown(f"- **tags:** {_documentation_detail_fallback(', '.join(selected.get('tags') or []))}")
        with detail_right:
            st.markdown("**Review state**")
            st.markdown(f"- **provenance_status:** {_documentation_detail_fallback(selected.get('provenance_status'))}")
            st.markdown(f"- **review_status:** {_documentation_detail_fallback(selected.get('review_status'))}")
            st.markdown(f"- **sequence_available:** {'Yes' if selected.get('sequence_available') else 'No'}")
            st.markdown(
                f"- **sequence_hash status:** "
                f"{_documentation_detail_fallback(selected.get('sequence_hash'), placeholder='Not recorded')}"
            )
        st.markdown("**Narrative notes**")
        st.markdown(f"- **short_description:** {_documentation_detail_fallback(selected.get('short_description'))}")
        st.markdown(
            f"- **organism_or_source_context:** "
            f"{_documentation_detail_fallback(selected.get('organism_or_source_context'))}"
        )
        st.markdown(f"- **source_notes:** {_documentation_detail_fallback(selected.get('source_notes'))}")
        st.markdown(f"- **human_review_notes:** {_documentation_detail_fallback(selected.get('human_review_notes'))}")
        st.markdown("**Host / chassis context readback**")
        st.markdown(f"- **recorded source context:** {host_context['source_value']}")
        st.markdown(f"- **normalized review context:** {host_context['normalized_context_label']}")
        st.caption("Recorded/source context only. This readback is not compatibility evidence, not a recommendation, and not a validation claim.")
        st.markdown("**Reference in project documentation**")
        st.markdown(
            f"- **record identifier:** "
            f"{_documentation_detail_fallback(selected.get('asset_id'), placeholder='Not recorded')}"
        )
        st.markdown(
            f"- **catalog source/status:** "
            f"{_documentation_detail_fallback(selected.get('provenance_status'), placeholder='Not recorded')} / "
            f"{_documentation_detail_fallback(selected.get('review_status'), placeholder='Not recorded')}"
        )
        st.markdown("- **workflow bridge:** Expression Wizard Step 6 catalog context or Pathway Workspace linked catalog assets")
        st.caption(
            _documentation_detail_fallback(
                selected.get("documentation_boundary_note"),
                placeholder="Documentation-only metadata record for review and traceability.",
            )
        )


def _render_generic_component_library_asset_readback(records: list[dict[str, object]]) -> None:
    st.subheader("Computed Component Library readback")
    st.caption(GENERIC_ASSET_READBACK_COPY)
    presenter = build_component_library_asset_readback_presenter(local_design_assets=records)
    st.caption(presenter["documentation_boundary_note"])
    if not presenter["rows"]:
        st.info(presenter["empty_state"])
        return

    summary = presenter["summary"]
    render_compact_summary_cards(
        [
            (
                "Readback asset rows",
                str(summary["total_asset_rows"]),
                _scope_caption("Local Design Asset Catalog", "computed readback rows", "readback rows"),
            ),
            (
                "Asset type groups",
                str(summary["asset_type_count"]),
                _scope_caption("Local Design Asset Catalog", "computed readback rows", "generic display labels"),
            ),
            (
                "Source/provenance rows",
                str(summary["rows_with_source_provenance_identity"]),
                _scope_caption("Local Design Asset Catalog", "computed readback rows", "source/provenance rows"),
            ),
            (
                "Evidence/review rows",
                str(summary["rows_with_evidence_review_metadata"]),
                _scope_caption("Local Design Asset Catalog", "computed readback rows", "review rows"),
            ),
        ]
    )
    st.caption(presenter["source_identity_note"])
    st.dataframe(
        pd.DataFrame(presenter["rows"])[presenter["columns"]],
        hide_index=True,
        use_container_width=True,
    )


def _render_component_library_contract_crosswalk_readback(records: list[dict[str, object]]) -> None:
    st.subheader("Component contract crosswalk readback")
    st.caption(CONTRACT_CROSSWALK_READBACK_COPY)
    presenter = build_component_library_contract_crosswalk_presenter(records)
    for note in presenter["boundary_notes"]:
        st.caption(str(note))
    if not presenter["components"]:
        st.info(presenter["empty_state"])
        return

    summary = presenter["summary"]
    render_compact_summary_cards(
        [
            (
                "Crosswalk components",
                str(summary["total_components"]),
                _scope_caption("Component Library", "existing records", "contract readback components"),
            ),
            (
                "Source/provenance shown",
                str(summary["components_with_source_provenance_context"]),
                _scope_caption("Component Library", "existing records", "source/provenance display status"),
            ),
            (
                "Evidence/reference shown",
                str(summary["components_with_evidence_reference_context"]),
                _scope_caption("Component Library", "existing records", "evidence/reference display status"),
            ),
            (
                "Missing-field follow-up",
                str(summary["components_with_missing_fields"]),
                _scope_caption("Component Library", "existing records", "manual documentation follow-up"),
            ),
        ]
    )

    first_component = presenter["components"][0]
    component_summary = first_component["component_summary"]
    st.markdown(f"**Component summary:** {component_summary['component_label']} ({component_summary['component_type']})")
    st.markdown(f"- Component ID: {component_summary['component_id']}")
    st.markdown(f"- Source/provenance: {first_component['source_provenance_display_status']}")
    st.markdown(f"- Evidence/reference: {first_component['evidence_reference_display_status']}")
    st.markdown(
        "- Missing fields: "
        + ("; ".join(first_component["missing_fields"]) if first_component["missing_fields"] else "No required field gaps recorded")
    )
    for note in first_component["follow_up_notes"]:
        st.markdown(f"- Follow-up note: {note}")

    group_rows = [
        {"Field group": "Required", "Fields": "; ".join(presenter["field_groups"]["required"])},
        {"Field group": "Optional", "Fields": "; ".join(presenter["field_groups"]["optional"])},
        {"Field group": "Deferred", "Fields": "; ".join(presenter["field_groups"]["deferred"])},
        {"Field group": "Out of scope", "Fields": "; ".join(presenter["field_groups"]["out_of_scope"])},
    ]
    st.dataframe(pd.DataFrame(group_rows), hide_index=True, use_container_width=True)

    rows = [
        {
            "Contract field": row["contract_field"],
            "Requirement": row["requirement"],
            "Display value": row["display_value"],
            "Recorded": "Yes" if row["recorded"] else "No",
            "Display treatment": row["display_treatment"],
        }
        for row in [*first_component["required_fields"], *first_component["optional_fields"][:8]]
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_component_library_followup_queue(records: list[dict[str, object]]) -> None:
    st.subheader("Source/provenance follow-up queue")
    presenter = build_component_library_followup_queue_presenter(records)
    st.caption(presenter["intro"])
    st.caption(presenter["boundary_note"])
    _render_component_library_followup_summary_panel(presenter["summary"])
    if not presenter["rows"]:
        st.info(presenter["empty_state"])
        return

    filtered_rows = _render_component_library_followup_filter_controls(presenter)
    st.caption(f"Filtered follow-up rows: {len(filtered_rows)} of {len(presenter['rows'])}")
    if not filtered_rows:
        st.info(presenter["filter_empty_state"])
        return

    st.caption("Detailed read-only queue rows preserve the existing R359 follow-up table.")
    st.dataframe(
        pd.DataFrame(filtered_rows)[presenter["columns"]],
        hide_index=True,
        use_container_width=True,
    )


def _render_component_library_followup_filter_controls(presenter: dict[str, object]) -> list[dict[str, object]]:
    st.markdown("**Read-only queue filters**")
    filter_options = presenter.get("filter_options")
    options = filter_options if isinstance(filter_options, dict) else {}
    followup_type_options = list(options.get("followup_types") or [])
    component_type_options = list(options.get("component_types") or [])
    selected_followup_types = st.multiselect(
        "Follow-up type",
        followup_type_options,
        default=[],
        key="component_library_followup_type_filter",
        placeholder="All follow-up types",
    )
    selected_component_types = st.multiselect(
        "Component type",
        component_type_options,
        default=[],
        key="component_library_followup_component_type_filter",
        placeholder="All component types",
    )
    rows = presenter.get("rows")
    row_list = rows if isinstance(rows, list) else []
    return filter_followup_queue_rows(
        row_list,
        followup_types=selected_followup_types,
        component_types=selected_component_types,
    )


def _render_component_library_followup_summary_panel(summary: dict[str, object]) -> None:
    st.markdown("**Follow-up summary grouping**")
    render_compact_summary_cards(
        [
            (
                "Follow-up rows",
                str(summary["total_followup_rows"]),
                _scope_caption("Component Library", "existing readback rows", "manual follow-up rows"),
            ),
            (
                "Records with follow-up",
                str(summary.get("records_with_followup", summary.get("components_with_followup", 0))),
                _scope_caption("Component Library", "existing readback rows", "records needing documentation review"),
            ),
            (
                "Missing source/provenance",
                str(summary.get("missing_source_provenance_count", 0)),
                _scope_caption("Component Library", "existing readback rows", "source/provenance follow-up"),
            ),
            (
                "Missing evidence/reference",
                str(summary.get("missing_evidence_reference_count", 0)),
                _scope_caption("Component Library", "existing readback rows", "evidence/reference follow-up"),
            ),
            (
                "Manual review rows",
                str(summary.get("needs_manual_review_count", 0)),
                _scope_caption("Component Library", "existing readback rows", "manual review rows"),
            ),
            (
                "Deferred / boundary rows",
                f"{summary.get('deferred_field_count', 0)} / {summary.get('boundary_note_count', 0)}",
                _scope_caption("Component Library", "existing readback rows", "deferred fields / boundary notes"),
            ),
        ]
    )
    summary_rows = summary.get("summary_rows")
    if summary_rows:
        st.dataframe(
            pd.DataFrame(summary_rows),
            hide_index=True,
            use_container_width=True,
        )


def _render_component_library_slot_browse(records: list[dict[str, object]]) -> None:
    st.subheader("Component records by plant expression construct context")
    st.caption(SLOT_FIRST_BROWSE_COPY)
    base_presenter = build_component_library_slot_browse_presenter(records)
    if not base_presenter["rows"]:
        st.info(base_presenter["empty_state"])
        st.caption("No slot detail is shown until existing Component Library records are available for review.")
        _render_advanced_component_evidence_readback(base_presenter)
        return

    slot_options = ["All plant expression construct contexts"] + list(base_presenter["slot_labels"])
    selected_slot = st.selectbox(
        "Plant expression construct context filter",
        options=slot_options,
        key="component_library_slot_browse_filter",
    )
    presenter = build_component_library_slot_browse_presenter(records, selected_slot_label=selected_slot)
    summary = presenter["summary"]
    render_compact_summary_cards(
        [
            (
                "Slot readback rows",
                str(summary["slot_row_count"]),
                _scope_caption("Component Library", "existing records", "plant expression construct context rows"),
            ),
            (
                "Slots with records",
                str(summary["slot_rows_with_records"]),
                _scope_caption("Component Library", "current context filter", "contexts containing records"),
            ),
            (
                "Source follow-up slots",
                str(summary["source_follow_up_slot_count"]),
                _scope_caption("Component Library", "current context filter", "source/provenance follow-up rows"),
            ),
            (
                "Manual follow-up slots",
                str(summary["manual_follow_up_slot_count"]),
                _scope_caption("Component Library", "current context filter", "manual follow-up rows"),
            ),
        ]
    )
    _render_component_library_slot_compact_details(presenter["rows"])
    st.dataframe(
        pd.DataFrame(presenter["rows"])[presenter["columns"]],
        hide_index=True,
        use_container_width=True,
    )
    _render_advanced_component_evidence_readback(base_presenter)


def _render_advanced_component_evidence_readback(presenter: dict[str, object]) -> None:
    with st.expander("Advanced component evidence readback", expanded=False):
        st.caption(ADVANCED_COMPONENT_EVIDENCE_COPY)
        st.caption(str(presenter["boundary_note"]))
        _render_component_library_slot_glossary()


def _render_component_library_slot_glossary() -> None:
    with st.expander("What do these terms mean?", expanded=False):
        st.caption(SLOT_FIRST_GLOSSARY_BOUNDARY_COPY)
        for term, definition in SLOT_FIRST_GLOSSARY_TERMS:
            st.markdown(f"- **{term}:** {definition}")


def _render_plant_mvp_context() -> None:
    st.markdown(f"**{PLANT_MVP_CONTEXT_TITLE}**")
    st.markdown(f"**{PLANT_MVP_CONTEXT_VALUE}**")
    st.caption(PLANT_MVP_CONTEXT_COPY)
    category_rows = [
        {"Plant component category": label, "Review focus": description}
        for label, description in PLANT_COMPONENT_CATEGORY_DESCRIPTIONS
    ]
    st.dataframe(pd.DataFrame(category_rows), hide_index=True, use_container_width=True)
    with st.expander("Plant component source/provenance review details", expanded=False):
        st.caption(DATA_SURFACE_SEPARATION_COPY)
        st.caption(DATA_SURFACE_BOUNDARY_COPY)
        st.caption(PLANT_SOURCE_PROVENANCE_DETAIL_COPY)
        st.markdown(
            "- Source identity, citation, file, vendor, database, or lab-note context\n"
            "- Provenance status and review-status readback\n"
            "- Host, tissue, compartment, expression-mode, marker, and backbone context when recorded"
        )
    with st.expander("Manual follow-up guidance", expanded=False):
        st.caption(MANUAL_FOLLOW_UP_GUIDANCE_COPY)
        for label, description in PLANT_COMPONENT_CATEGORY_DESCRIPTIONS:
            st.markdown(f"- **{label}:** {description}.")


def _render_component_library_slot_compact_details(rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with st.expander("Compact slot details for narrow screens", expanded=False):
        st.caption(SLOT_COMPACT_DETAIL_COPY)
        for row in rows:
            slot = _documentation_detail_fallback(row.get("Slot"))
            record_count = _documentation_detail_fallback(row.get("Record count"), placeholder="0")
            records = _documentation_detail_fallback(row.get("Records"))
            source_status = _documentation_detail_fallback(row.get("Source/provenance status"))
            manual_follow_up = _documentation_detail_fallback(row.get("Manual follow-up"))
            st.markdown(f"**{slot}**")
            st.markdown(f"- Records: {record_count} | {records}")
            st.markdown(f"- Source/provenance: {source_status}")
            st.markdown(f"- Manual follow-up: {manual_follow_up}")


def _render_component_library_workflow_entry(
    records: list[dict[str, object]],
    *,
    saved_registry_record_count: int,
) -> None:
    base_presenter = build_component_library_workflow_entry_presenter(
        records,
        saved_registry_record_count=saved_registry_record_count,
    )
    render_tool_intro(base_presenter["title"], base_presenter["intro"])
    render_boundary_note(base_presenter["boundary_note"])

    if not base_presenter["rows"]:
        st.info(base_presenter["empty_state"])
        return

    slot_cards = [
        (
            row["Slot"],
            f"{row['Record count']} record(s)",
            f"source/provenance review: {row['Source/provenance review']}; manual review: {row['Manual review']}",
        )
        for row in base_presenter["slot_groups"][:4]
    ]
    st.markdown("**Available workflow slot groups**")
    render_compact_summary_cards(slot_cards)
    if len(base_presenter["slot_groups"]) > len(slot_cards):
        st.caption(
            f"{len(base_presenter['slot_groups']) - len(slot_cards)} additional slot group(s) are available in the filters and full detail rows."
        )

    st.markdown("**First-screen filters**")
    filter_options = base_presenter["filter_options"]
    filter_top_cols = st.columns(2)
    with filter_top_cols[0]:
        selected_slot = st.selectbox(
            "Slot",
            options=[ALL_SLOT_FILTER] + list(filter_options["slots"]),
            key="component_library_workflow_slot_filter",
        )
    with filter_top_cols[1]:
        selected_type = st.selectbox(
            "Component type",
            options=[ALL_TYPE_FILTER] + list(filter_options["component_types"]),
            key="component_library_workflow_type_filter",
        )
    filter_bottom_cols = st.columns(2)
    with filter_bottom_cols[0]:
        selected_source = st.selectbox(
            "Source/provenance",
            options=[ALL_SOURCE_FILTER] + list(filter_options["source_statuses"]),
            key="component_library_workflow_source_filter",
        )
    with filter_bottom_cols[1]:
        selected_followup = st.selectbox(
            "Follow-up",
            options=[ALL_FOLLOWUP_FILTER] + list(filter_options["followup_statuses"]),
            key="component_library_workflow_followup_filter",
        )

    presenter = build_component_library_workflow_entry_presenter(
        records,
        saved_registry_record_count=saved_registry_record_count,
        slot=selected_slot,
        component_type=selected_type,
        source_status=selected_source,
        followup_status=selected_followup,
    )
    summary = presenter["summary"]
    render_compact_summary_cards(
        [
            (
                "All component records",
                str(summary["total_records"]),
                "saved registry rows plus workflow entry records",
            ),
            (
                "Filtered records",
                str(summary["filtered_records"]),
                "current first-screen filter match",
            ),
            (
                "Records with provenance",
                str(summary["records_with_source_provenance"]),
                "workflow records with source/provenance recorded",
            ),
            (
                "Missing provenance review",
                str(summary["records_needing_source_provenance_review"]),
                "workflow records needing source/provenance review",
            ),
            (
                "Needs follow-up",
                str(summary["records_needing_manual_review"]),
                "workflow records needing manual review",
            ),
            (
                "Slot groups",
                str(summary["slot_group_count"]),
                "workflow slot groups represented",
            ),
        ]
    )
    if summary["records_needing_source_provenance_review"] or summary["records_needing_manual_review"]:
        st.warning(
            "Review cue: some Component Library records need source/provenance review or manual follow-up before they are cited in documentation."
        )
    else:
        st.info("No source/provenance or manual follow-up cue is flagged by this workflow entry view.")

    if not presenter["filtered_rows"]:
        st.info("No component records match the current workflow filters. Adjust the filters or open full details below.")
    else:
        st.markdown("**Filtered record cards**")
        card_rows = [
            (
                row["Component label"],
                f"{row['Component type']} | {row['Slot']}",
                f"{row['Source/provenance status']} | {row['Follow-up status']}",
            )
            for row in presenter["cards"]
        ]
        render_compact_summary_cards(card_rows)
        if len(presenter["filtered_rows"]) > len(presenter["cards"]):
            st.caption(
                f"Showing {len(presenter['cards'])} first-screen card(s); {len(presenter['filtered_rows']) - len(presenter['cards'])} more match in full detail rows."
            )

    with st.expander("Full workflow detail rows", expanded=False):
        st.caption(
            "Full filtered workflow rows preserve slot, type, source/provenance status, follow-up status, review status, and record detail."
        )
        if presenter["filtered_rows"]:
            st.dataframe(
                pd.DataFrame(presenter["filtered_rows"])[presenter["columns"]],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("No full workflow detail rows match the current filters.")


def _render_legacy_registry_type_counts(all_df: pd.DataFrame) -> None:
    counts: dict[str, int] = {pt: 0 for pt in ALLOWED_TYPES}
    for pt_val in all_df["Type"].tolist():
        if pt_val in counts:
            counts[pt_val] += 1

    with st.expander("Legacy registry type counts", expanded=False):
        st.caption("Legacy registry browse counts are separate from the Parts Registry, Local Design Asset Catalog, and promoter catalog summaries above.")
        stat_cols = st.columns(len(ALLOWED_TYPES) + 1)
        for col, pt in zip(stat_cols, ALLOWED_TYPES):
            col.metric(pt, counts[pt])
        stat_cols[-1].metric(_t("data.total"), len(all_df))


def _render_top_summary(
    *,
    part_count: int,
    local_asset_count: int,
    source_review_needed_count: int,
    human_review_needed_count: int,
    readback_row_count: int,
) -> None:
    render_compact_summary_cards(
        [
            (
                "Saved component asset records",
                str(part_count),
                _scope_caption("Parts Registry", "saved local rows", "asset records"),
            ),
            (
                "Built-in design asset records",
                str(local_asset_count),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "asset records"),
            ),
            (
                "Source/provenance review rows",
                str(source_review_needed_count),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "review rows"),
            ),
            (
                "Human review rows",
                str(human_review_needed_count),
                _scope_caption("Local Design Asset Catalog", "bundled seed/catalog records", "review rows"),
            ),
            (
                "Computed readback rows",
                str(readback_row_count),
                _scope_caption("Local Design Asset Catalog", "computed readback rows", "readback rows"),
            ),
        ]
    )


def render() -> None:
    inject_tool_typography_css()
    render_tool_header(_t('data.title'), _t("data.subtitle"))
    st.caption(COMPONENT_OVERVIEW_COPY)
    all_df = _load_parts()
    local_design_catalog = load_local_design_asset_seed_catalog()
    local_design_records = local_design_catalog["records"]
    local_design_inventory = summarize_local_design_asset_inventory(local_design_records)
    local_design_review_counts = summarize_local_design_asset_review_status(local_design_records)
    _render_component_library_workflow_entry(
        local_design_records,
        saved_registry_record_count=len(all_df),
    )
    with st.expander("Component category glossary and boundary detail", expanded=False):
        _render_plant_mvp_context()
    with st.expander("Count scope summary", expanded=False):
        _render_top_summary(
            part_count=len(all_df),
            local_asset_count=int(local_design_inventory["total_record_count"]),
            source_review_needed_count=int(local_design_review_counts["source_review_needed"]),
            human_review_needed_count=int(local_design_review_counts["human_review_needed"]),
            readback_row_count=len(build_component_library_asset_readback_presenter(local_design_assets=local_design_records)["rows"]),
        )
        st.caption(
            "Saved component asset records, built-in design asset records, and computed readback rows are separate count scopes."
        )
    with st.expander("Full slot browse detail table", expanded=False):
        _render_component_library_slot_browse(local_design_records)
    st.caption(CORE_BROWSING_COPY)
    with st.expander("Parts Registry boundary", expanded=False):
        st.caption(_REGISTRY_MUTATION_NOTICE)

    st.subheader("Core component browsing")
    render_read_only_parts_catalog(show_admin=False)
    st.divider()
    _render_local_design_asset_catalog()
    _render_legacy_registry_type_counts(all_df)
    st.divider()

    st.subheader("Review / source follow-up")
    st.caption(REVIEW_FOLLOWUP_COPY)
    render_help_text(PROMOTER_ASSET_ENTRY_COPY)
    st.caption(PROMOTER_ASSET_DETAIL_COPY)
    st.caption(PROMOTER_ASSET_BOUNDARY_COPY)
    st.caption(
        _scope_caption(
            "Plant Promoter Catalog",
            "profile rows plus tissue evidence, motif, and review rows",
            "profile records and child review/readback rows",
        )
    )
    with st.expander("Plant promoter asset context", expanded=False):
        render_plant_promoter_catalog()
    with st.expander("Computed Component Library readback rows", expanded=False):
        _render_generic_component_library_asset_readback(local_design_records)
        _render_component_library_contract_crosswalk_readback(local_design_records)
        _render_component_library_followup_queue(local_design_records)
    st.subheader("Documentation preview / readback actions")
    with st.expander("Saved documentation artifacts", expanded=False):
        _render_documentation_artifact_library()
    st.subheader("Admin / diagnostic / write controls")
    with st.expander("Registry admin and write controls", expanded=False):
        st.caption(ADMIN_DIAGNOSTIC_COPY)
        if st.button(_t("data.register_new"), type="primary", use_container_width=True, key="open_register_dialog"):
            _register_dialog()

        tab_labels = list(_TAB_LABELS.values()) + [_t("data.tab.all")]
        tabs = st.tabs(tab_labels)
        for tab, pt in zip(tabs[:-1], ALLOWED_TYPES):
            with tab:
                st.subheader(f"{_TAB_LABELS.get(pt, pt)} Reference Records")
                _render_part_table(filter_type=pt, tab_key=pt.lower())
        with tabs[-1]:
            st.subheader(_t("data.tab.all"))
            _render_part_table(filter_type=None, tab_key="all")


