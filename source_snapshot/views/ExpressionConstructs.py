from __future__ import annotations

import pandas as pd
import streamlit as st

from core.session_keys import SK
from services import expression_cassette_slot_rows_presenter as slot_rows_presenter
from services import expression_construct_presenter as presenter
from services import expression_construct_repository as repo
from services import plant_promoter_catalog_presenter as promoter_presenter
from services import target_design_router
from services import target_design_router_preview
from services import target_design_router_preview_report
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_section_heading,
    render_subsection_heading,
    render_tool_header,
    render_tool_intro,
)


PAGE_TITLE = "Expression Constructs"
PAGE_SUBTITLE = "Editable local draft workflow for multi-gene construct documentation records."
BOUNDARY_COPY = (
    "Documentation-only construct workspace for local draft records, cassette rows, cassette parts, linked genes, "
    "and linked pathway references. This page does not recommend, score, rank, optimize, validate, or predict construct behavior."
)
INTRO_COPY = (
    "Create and update local construct drafts here, then review the current construct preview and browse tables without changing "
    "Expression Wizard behavior or importing external datasets."
)
FILTER_HELP_COPY = (
    "Filters narrow the local documentation view only. Editable draft controls below keep blank optional fields visible as review gaps."
)
TARGET_PREVIEW_HELP_COPY = (
    "Read-only documentation route preview for construct-draft review. Try example target text such as GOI, HSA, "
    "artemisinin precursor, or sugarcane healthy sugar; the preview is not saved as a record and does not create "
    "construct, cassette, source, or database rows."
)
TARGET_PREVIEW_BOUNDARY_COPY = (
    "Documentation-only construct draft preview for manual review and source confirmation. "
    "This panel does not create records, validate experiments, recommend parts, predict performance, "
    "or judge downstream use."
)
TARGET_PREVIEW_SCAN_COPY = (
    "Scan Target summary first, then Design route, Construct draft, Slots, Missing fields, Source requirements, "
    "Review notes, Markdown readback, and Boundary note."
)
TARGET_PREVIEW_REVIEW_HELP_COPY = (
    "Use this checklist as a read-only review aid. Missing fields and source requirements are prompts for manual "
    "documentation follow-up and source confirmation, not biological scoring or part selection."
)
TARGET_PREVIEW_READBACK_COPY = (
    "Read-only Markdown readback for documentation review only. It is copyable review text that mirrors the current "
    "preview; it is not saved as a record and does not change export or package schema."
)
TARGET_PREVIEW_EMPTY_TABLE_COPY = {
    "Gene slots": (
        "No gene slots are shown because target clarification is required before any gene or pathway identity is drafted."
    ),
    "Cassette slots": (
        "No cassette slots are available until the route is clarified; sugarcane healthy sugar and unknown targets "
        "remain target-clarification previews."
    ),
    "Required parts": (
        "No required-part rows are shown until a route is clarified; this empty table is not a complete design."
    ),
}
COMPONENT_READBACK_COPY = (
    "Read-only component readback for the selected construct draft. It lists documented component labels, cassette "
    "context, source/reference context, sequence-availability notes, and review gaps for manual documentation review only. "
    "Use the Source/reference context and Record review status columns to decide whether the row needs source review, "
    "provenance review, or manual follow-up in this existing review surface."
)
STEP2_COMPONENT_CONTEXT_READBACK_COPY = (
    "Read-only review context from the current Expression Wizard Step 2 Component Library context presenter. "
    "These rows show recorded Component Library context, source/provenance review, record review status, "
    "sequence metadata, and manual follow-up only."
)
CASSETTE_SLOT_PREVIEW_COPY = (
    "Read-only cassette slot preview for the selected construct draft. It maps existing record readback into "
    "expression-vector-first slots so source/provenance gaps and manual follow-up stay visible without changing "
    "saved records, package output, sequence assembly, component choice, or workflow behavior."
)
CASSETTE_SLOT_PREVIEW_EMPTY_COPY = (
    "No construct record data is available for this preview yet. The rows below show manual documentation gaps "
    "and optional empty slots only; they are prompts for existing record readback, not auto-fixes or recommendations."
)
COMPONENT_REVIEW_SUMMARY_COPY = (
    "Read-only construct review summary derived from the current component rows. Counts support manual documentation "
    "review and do not rank, validate, recommend, or judge downstream-use state."
)
COMPONENT_FOLLOW_UP_QUEUE_COPY = (
    "Manual documentation follow-up queue for construct component rows. Each item points to source/reference, "
    "provenance, sequence-availability, role-label, duplicate-label, or review-note context for human "
    "documentation review. The Documentation follow-up type column names the review need; the Manual review detail "
    "column explains the gap to inspect."
)
COMPONENT_REVIEW_ACTION_CUE_COPY = (
    "This cue appears when existing component documentation follow-up rows need easier review on the source page. "
    "It summarizes only the current role-label and duplicate-label documentation rows for the selected "
    "construct/cassette context."
)
COMPONENT_REVIEW_ACTION_CUE_MANUAL_COPY = (
    "Manual action remains: inspect the listed component labels, cassette context, documentation follow-up type, "
    "manual review detail, and manual documentation review note in the queue below. The cue does not resolve "
    "biological questions or change saved records."
)
COMPONENT_REVIEW_NEXT_STEP_COPY = (
    "Next documentation step: use the queue below to add or update source/reference, provenance, role-label, "
    "duplicate-label, sequence-availability, or review-note context in the local construct draft records."
)
COMPONENT_REVIEW_ACTION_CUE_EMPTY_COPY = (
    "No role-label or duplicate-label documentation follow-up rows are visible for this construct/cassette selection. "
    "This only describes the current documentation queue; broader manual review may still be needed."
)
REVIEW_GAP_COPY = (
    "Review gaps keep missing source, provenance, source-record, link, and review-note context visible for manual "
    "follow-up. They are not scoring, ranking, biological recommendation, or downstream-use judgments."
)
TARGET_TYPE_OPTIONS = ["", "gene", "single gene", "protein", "pathway", "trait"]
HOST_CATEGORY_OPTIONS = ["", "plant", "microbial", "mammalian", "other"]
TARGET_PREVIEW_FIELD_LABELS = {
    "target_label": "Target label",
    "aliases": "Aliases",
    "notes": "Notes",
    "design_route": "Design route",
    "route_label": "Route label",
    "review_status": "Review status",
    "support_status": "Support status",
    "template_id": "Template ID",
    "template_label": "Template label",
    "description": "Description",
    "structure": "Structure",
}
TARGET_PREVIEW_COLUMN_LABELS = {
    "slot": "Slot",
    "gene_label": "Gene",
    "slot_role": "Role",
    "source_requirement": "Source requirement",
    "review_status": "Review status",
    "cassette": "Cassette draft",
    "cassette_slot": "Cassette slot",
    "part_slot": "Part slot",
    "slot_label": "Slot label",
    "source_status": "Source status",
    "item": "Item",
    "status": "Status",
    "review_action": "Review action",
    "field": "Field",
}
TABLE_COLUMNS = presenter.TABLE_COLUMNS
CASSETTE_COLUMNS = presenter.CASSETTE_COLUMNS
PART_COLUMNS = presenter.PART_COLUMNS
GENE_COLUMNS = presenter.GENE_COLUMNS
PATHWAY_COLUMNS = presenter.PATHWAY_COLUMNS
PROJECT_LINK_COLUMNS = presenter.PROJECT_LINK_COLUMNS
COMPONENT_COLUMNS = presenter.COMPONENT_COLUMNS
COMPONENT_GAP_QUEUE_COLUMNS = presenter.COMPONENT_GAP_QUEUE_COLUMNS
COMPONENT_GAP_QUEUE_DISPLAY_COLUMNS = [
    "Construct label",
    "Cassette label",
    "Component label",
    "Component category",
    "Documentation follow-up type",
    "Manual review detail",
    "Manual documentation review note",
]
COMPONENT_GAP_QUEUE_DISPLAY_LABELS = {
    "Issue type": "Documentation follow-up type",
    "Issue detail": "Manual review detail",
    "Manual follow-up note": "Manual documentation review note",
}
STEP2_COMPONENT_CONTEXT_COLUMNS = presenter.STEP2_COMPONENT_CONTEXT_COLUMNS
CASSETTE_SLOT_PREVIEW_COLUMNS = [
    "Slot",
    "Recorded value",
    "Source / provenance",
    "Review status",
    "Gap / follow-up",
]
CASSETTE_SLOT_PREVIEW_GROUPS = [
    (
        "Target and source context",
        ("target_gene_cds_protein", "sequence_source_provenance", "expression_host"),
        "Review the recorded target, source/provenance, and host context before scanning cassette elements.",
    ),
    (
        "Expression cassette elements",
        (
            "promoter",
            "rbs_kozak_5utr",
            "signal_peptide",
            "cds_insert",
            "fusion_tag",
            "linker",
            "terminator_polya",
        ),
        "Read-only element readback from existing records; blank optional rows stay visible as documentation gaps.",
    ),
    (
        "Vector and selection context",
        ("selectable_marker_reporter", "vector_backbone", "component_source"),
        "Review vector, marker/reporter, and component source/provenance context without part ranking or selection advice.",
    ),
    (
        "Review checks and follow-up",
        ("sequence_basic_checks", "gap_follow_up_review"),
        "Manual follow-up rows keep not assessed checks and documentation gaps visible for human review.",
    ),
]
GAP_COLUMNS = presenter.GAP_COLUMNS
SELECTED_CONSTRUCT_KEY = "expression_construct_selected_construct_id"
COMPONENT_REVIEW_ACTION_ISSUE_TYPES = (
    presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
    presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
)


def _text(value: object, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _row_list(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _promoter_source_options() -> list[dict[str, str]]:
    view_model = promoter_presenter.build_plant_promoter_catalog_view_model()
    evidence_rows = _row_list(view_model.get("evidence_rows") if isinstance(view_model, dict) else [])
    profile_rows = _row_list(view_model.get("profile_rows") if isinstance(view_model, dict) else [])
    by_part_id: dict[str, dict[str, str]] = {}

    for row in profile_rows:
        part_id = _text(row.get("part_id"))
        if not part_id:
            continue
        by_part_id.setdefault(
            part_id,
            {
                "record_id": part_id,
                "record_label": _text(row.get("display_name"), part_id),
                "select_label": f"{_text(row.get('display_name'), part_id)} / {part_id}",
                "context_note": "Component Library promoter asset record; no tissue evidence row selected.",
            },
        )

    for row in evidence_rows:
        part_id = _text(row.get("part_id"))
        if not part_id:
            continue
        record_label = _text(row.get("promoter_label"), part_id)
        context_values = [
            _text(row.get("plant_clade"), promoter_presenter.NO_CLADE_LABEL),
            _text(row.get("species_label"), promoter_presenter.NO_SPECIES_LABEL),
            _text(row.get("tissue_context"), promoter_presenter.NO_TISSUE_LABEL),
            _text(row.get("evidence_type"), promoter_presenter.NO_EVIDENCE_TYPE_LABEL),
            _text(row.get("source_database"), promoter_presenter.NO_SOURCE_LABEL),
            _text(row.get("curation_status"), promoter_presenter.NO_CURATION_STATUS_LABEL),
            _text(row.get("review_note"), "No review note recorded"),
        ]
        context_note = " | ".join(context_values)
        by_part_id[part_id] = {
            "record_id": part_id,
            "record_label": record_label,
            "select_label": f"{record_label} / {part_id}",
            "context_note": context_note,
        }

    return sorted(by_part_id.values(), key=lambda row: row["select_label"].casefold())


def _sanitize_view_model(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raw = {}
    summary = raw.get("summary_counts")
    if not isinstance(summary, dict):
        summary = {}
    component_summary = raw.get("construct_component_review_summary")
    if not isinstance(component_summary, dict):
        component_summary = {}
    draft_defaults = raw.get("draft_defaults") if isinstance(raw.get("draft_defaults"), dict) else {}
    empty_states = raw.get("empty_states") if isinstance(raw.get("empty_states"), dict) else {}
    step2_context = raw.get("step2_component_context_readback")
    if not isinstance(step2_context, dict):
        step2_context = {}
    step2_summary = step2_context.get("summary") if isinstance(step2_context.get("summary"), dict) else {}
    return {
        "summary_counts": {
            "construct_profile_count": int(summary.get("construct_profile_count") or 0),
            "cassette_count": int(summary.get("cassette_count") or 0),
            "cassette_part_count": int(summary.get("cassette_part_count") or 0),
            "gene_link_count": int(summary.get("gene_link_count") or 0),
            "pathway_step_link_count": int(summary.get("pathway_step_link_count") or 0),
            "project_link_count": int(summary.get("project_link_count") or 0),
            "review_gap_count": int(summary.get("review_gap_count") or 0),
        },
        "construct_profile_rows": _row_list(raw.get("construct_profile_rows")),
        "cassette_rows": _row_list(raw.get("cassette_rows")),
        "cassette_part_rows": _row_list(raw.get("cassette_part_rows")),
        "construct_component_rows": _row_list(raw.get("construct_component_rows")),
        "construct_component_review_summary": {
            "total_component_rows": int(component_summary.get("total_component_rows") or 0),
            "rows_with_source_reference_context": int(component_summary.get("rows_with_source_reference_context") or 0),
            "rows_missing_source_reference_context": int(component_summary.get("rows_missing_source_reference_context") or 0),
            "rows_with_sequence_availability_note": int(component_summary.get("rows_with_sequence_availability_note") or 0),
            "rows_with_review_metadata_status": int(component_summary.get("rows_with_review_metadata_status") or 0),
            "rows_with_review_note": int(component_summary.get("rows_with_review_note") or 0),
            "rows_needing_manual_follow_up": int(component_summary.get("rows_needing_manual_follow_up") or 0),
        },
        "construct_component_gap_queue": _row_list(raw.get("construct_component_gap_queue")),
        "step2_component_context_readback": {
            "title": _text(step2_context.get("title"), presenter.STEP2_CONTEXT_READBACK_TITLE),
            "subtitle": _text(step2_context.get("subtitle"), presenter.STEP2_CONTEXT_READBACK_COPY),
            "rows": _row_list(step2_context.get("rows")),
            "summary": {
                "total_rows": int(step2_summary.get("total_rows") or 0),
                "rows_with_recorded_assets": int(step2_summary.get("rows_with_recorded_assets") or 0),
                "manual_follow_up_rows": int(step2_summary.get("manual_follow_up_rows") or 0),
            },
            "empty_state": _text(step2_context.get("empty_state"), presenter.STEP2_CONTEXT_EMPTY_STATE),
            "documentation_boundary_note": _text(
                step2_context.get("documentation_boundary_note"),
                presenter.STEP2_CONTEXT_BOUNDARY_NOTE,
            ),
        },
        "linked_gene_rows": _row_list(raw.get("linked_gene_rows")),
        "linked_pathway_step_rows": _row_list(raw.get("linked_pathway_step_rows")),
        "project_link_rows": _row_list(raw.get("project_link_rows")),
        "review_gap_rows": _row_list(raw.get("review_gap_rows")),
        "boundary_copy": _text(raw.get("boundary_copy"), presenter.BOUNDARY_COPY),
        "draft_defaults": {
            "construct_label": _text(draft_defaults.get("construct_label"), presenter.DEFAULT_CONSTRUCT_LABEL),
            "construct_type": _text(draft_defaults.get("construct_type"), presenter.DEFAULT_CONSTRUCT_TYPE),
            "cassette_label": _text(draft_defaults.get("cassette_label"), presenter.DEFAULT_CASSETTE_LABEL),
            "cassette_role": _text(draft_defaults.get("cassette_role"), presenter.DEFAULT_CASSETTE_TYPE),
            "review_status": _text(draft_defaults.get("review_status"), "draft documentation review"),
        },
        "empty_states": {
            "constructs": _text(empty_states.get("constructs"), "No construct drafts are present yet."),
            "cassettes": _text(empty_states.get("cassettes"), "No cassette rows are recorded for the selected construct draft yet."),
            "parts": _text(empty_states.get("parts"), "No cassette part rows are recorded for the selected cassette yet."),
            "project_links": _text(empty_states.get("project_links"), "No project-level construct links are recorded yet."),
        },
    }


def _current_step2_component_context_readback() -> dict[str, object]:
    ds = st.session_state.get(SK.DESIGN_SESSION)
    host = _text(getattr(ds, "host", ""))
    tag = _text(getattr(ds, "tag", ""))
    elements = getattr(ds, "elements", {})
    rules: dict[str, object] = {}
    if host:
        try:
            from core.expression_frame_builder import get_host_rules

            loaded_rules = get_host_rules(host)
            rules = loaded_rules if isinstance(loaded_rules, dict) else {}
        except Exception:
            rules = {}
    return presenter.build_step2_component_context_readback(
        host=host,
        tag=tag,
        rules=rules,
        elements=elements if isinstance(elements, dict) else {},
    )


def _construct_type_options(rows: list[dict[str, object]]) -> list[str]:
    return presenter.construct_type_options(rows)


def _construct_status_options(rows: list[dict[str, object]]) -> list[str]:
    return presenter.construct_status_options(rows)


def _selected_value(label: str, options: list[str], key: str, *, index: int = 0) -> str:
    return st.selectbox(label, options=options, key=key, index=index if options else 0)


def _display_field_label(field: str) -> str:
    return TARGET_PREVIEW_FIELD_LABELS.get(field, field.replace("_", " ").title())


def _display_preview_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {TARGET_PREVIEW_COLUMN_LABELS.get(str(key), str(key).replace("_", " ").title()): value for key, value in row.items()}
        for row in rows
    ]


def _field_value_rows(values: dict[str, object], keys: list[str], *, list_separator: str = " | ") -> list[dict[str, object]]:
    rows = []
    for key in keys:
        value = values.get(key)
        if isinstance(value, list):
            value = list_separator.join(_text(item) for item in value if _text(item))
        rows.append({"Field": _display_field_label(key), "Value": _text(value, "Not recorded")})
    return rows


def _render_preview_table(title: str, rows: list[dict[str, object]], columns: list[str] | None = None) -> None:
    render_subsection_heading(title)
    if rows:
        display_rows = _display_preview_rows(rows)
        frame = pd.DataFrame(display_rows)
        if columns:
            display_columns = [TARGET_PREVIEW_COLUMN_LABELS.get(column, column.replace("_", " ").title()) for column in columns]
            frame = pd.DataFrame(display_rows, columns=display_columns)
        st.dataframe(frame, hide_index=True, use_container_width=True)
        return
    st.caption(
        TARGET_PREVIEW_EMPTY_TABLE_COPY.get(
            title,
            f"No {title.lower()} are shown yet; this route preview has no entries to review in this table.",
        )
    )


def _component_follow_up_queue_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    table_rows = presenter.construct_component_gap_queue_table_rows(rows)
    return pd.DataFrame(table_rows, columns=COMPONENT_GAP_QUEUE_COLUMNS).rename(columns=COMPONENT_GAP_QUEUE_DISPLAY_LABELS)


def _cassette_slot_preview_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Slot": row.get("slot_label", ""),
                "Recorded value": row.get("recorded_value", ""),
                "Source / provenance": row.get("source_or_provenance", ""),
                "Review status": row.get("review_status", ""),
                "Gap / follow-up": row.get("gap_or_follow_up", ""),
            }
            for row in rows
        ],
        columns=CASSETTE_SLOT_PREVIEW_COLUMNS,
    )


def _cassette_slot_rows_by_group(rows: list[dict[str, object]]) -> list[tuple[str, str, list[dict[str, object]]]]:
    by_key = {str(row.get("slot_key", "")): row for row in rows}
    grouped_rows = []
    rendered_keys: set[str] = set()
    for title, slot_keys, help_text in CASSETTE_SLOT_PREVIEW_GROUPS:
        group = [by_key[slot_key] for slot_key in slot_keys if slot_key in by_key]
        rendered_keys.update(slot_keys)
        grouped_rows.append((title, help_text, group))

    remaining = [row for row in rows if str(row.get("slot_key", "")) not in rendered_keys]
    if remaining:
        grouped_rows.append(
            (
                "Additional recorded slot readback",
                "Read-only fallback group for backward-compatible presenter rows not yet assigned to a display section.",
                remaining,
            )
        )
    return grouped_rows


def _render_cassette_slot_preview(
    *,
    profile_rows: list[dict[str, object]],
    cassette_rows: list[dict[str, object]],
    part_rows: list[dict[str, object]],
    component_rows: list[dict[str, object]],
    step2_component_context_readback: dict[str, object],
    gene_rows: list[dict[str, object]],
    gap_rows: list[dict[str, object]],
) -> None:
    slot_preview = slot_rows_presenter.build_expression_cassette_slot_rows_presenter(
        target_record=gene_rows[0] if gene_rows else None,
        sequence_source_record=gene_rows[0] if gene_rows else None,
        construct_profile=profile_rows[0] if profile_rows else None,
        cassette_rows=cassette_rows,
        cassette_part_rows=part_rows,
        component_rows=component_rows,
        step2_context_rows=_row_list(step2_component_context_readback.get("rows")),
        gap_review_records=gap_rows,
    )
    rows = _row_list(slot_preview.get("rows"))
    summary = slot_preview.get("summary") if isinstance(slot_preview.get("summary"), dict) else {}

    render_section_heading("Read-only cassette slot preview")
    st.caption(CASSETTE_SLOT_PREVIEW_COPY)
    st.caption(_text(slot_preview.get("documentation_boundary_note"), slot_rows_presenter.SAFETY_BOUNDARY_NOTE))
    if not any(profile_rows + cassette_rows + part_rows + component_rows + gene_rows + gap_rows):
        st.info(CASSETTE_SLOT_PREVIEW_EMPTY_COPY)
    render_compact_summary_cards(
        [
            ("Slot rows", str(int(summary.get("total_slot_rows") or len(rows))), "expression cassette review"),
            ("Documented rows", str(int(summary.get("documented_rows") or 0)), "existing record readback"),
            ("Manual follow-up", str(int(summary.get("manual_follow_up_rows") or 0)), "documentation gap review"),
        ]
    )
    for group_title, group_help, group_rows in _cassette_slot_rows_by_group(rows):
        render_subsection_heading(group_title)
        st.caption(group_help)
        st.dataframe(_cassette_slot_preview_frame(group_rows), hide_index=True, use_container_width=True)


def _render_step2_component_context_readback(readback: dict[str, object]) -> None:
    render_section_heading(_text(readback.get("title"), presenter.STEP2_CONTEXT_READBACK_TITLE))
    st.caption(STEP2_COMPONENT_CONTEXT_READBACK_COPY)
    st.caption(_text(readback.get("documentation_boundary_note"), presenter.STEP2_CONTEXT_BOUNDARY_NOTE))
    summary = readback.get("summary") if isinstance(readback.get("summary"), dict) else {}
    render_compact_summary_cards(
        [
            ("Context rows", str(int(summary.get("total_rows") or 0)), "read-only review context"),
            ("Recorded assets", str(int(summary.get("rows_with_recorded_assets") or 0)), "source/provenance review"),
            ("Manual follow-up", str(int(summary.get("manual_follow_up_rows") or 0)), "review context"),
        ]
    )
    rows = _row_list(readback.get("rows"))
    if not rows:
        st.info(_text(readback.get("empty_state"), presenter.STEP2_CONTEXT_EMPTY_STATE))
        return
    st.dataframe(
        pd.DataFrame(presenter.step2_component_context_table_rows(rows), columns=STEP2_COMPONENT_CONTEXT_COLUMNS),
        hide_index=True,
        use_container_width=True,
    )


def _component_review_action_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if _text(row.get("Issue type")) in COMPONENT_REVIEW_ACTION_ISSUE_TYPES]


def _render_component_review_action_cue(component_gap_queue: list[dict[str, object]]) -> None:
    action_rows = _component_review_action_rows(component_gap_queue)
    total_follow_up_count = len(component_gap_queue)
    role_review_count = sum(
        1 for row in action_rows if _text(row.get("Issue type")) == presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE
    )
    duplicate_label_count = sum(
        1 for row in action_rows if _text(row.get("Issue type")) == presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE
    )

    render_section_heading("Component documentation follow-up")
    st.caption(COMPONENT_REVIEW_ACTION_CUE_COPY)
    st.caption(COMPONENT_REVIEW_ACTION_CUE_MANUAL_COPY)
    render_compact_summary_cards(
        [
            ("All follow-up rows", str(total_follow_up_count), "manual documentation review"),
            ("Role-label review", str(role_review_count), "manual documentation review"),
            ("Duplicate-label review", str(duplicate_label_count), "manual documentation review"),
        ]
    )
    if total_follow_up_count:
        st.caption(COMPONENT_REVIEW_NEXT_STEP_COPY)
    if not action_rows:
        st.caption(COMPONENT_REVIEW_ACTION_CUE_EMPTY_COPY)
        return

    for row in action_rows[:3]:
        issue_type = _text(row.get("Issue type"), "Documentation context needs review")
        component_label = _text(row.get("Component label"), presenter.NO_PART_LABEL)
        cassette_label = _text(row.get("Cassette label"), presenter.DEFAULT_CASSETTE_LABEL)
        st.caption(f"{issue_type}: {component_label} / {cassette_label}")
    if len(action_rows) > 3:
        st.caption(f"{len(action_rows) - 3} additional role/label documentation follow-up row(s) are visible below.")


def _render_target_design_preview_panel() -> None:
    render_section_heading("Target Design Preview")
    render_help_text(TARGET_PREVIEW_HELP_COPY)
    render_boundary_note(TARGET_PREVIEW_BOUNDARY_COPY)

    with st.expander("Target Design Route Preview", expanded=True):
        input_cols = st.columns(2)
        with input_cols[0]:
            target_name = st.text_input(
                "Target name",
                value="",
                key="target_design_preview_target_name",
                help="Example-only entries: GOI, HSA, artemisinin precursor, sugarcane healthy sugar.",
            )
            target_type = st.selectbox(
                "Target type",
                options=TARGET_TYPE_OPTIONS,
                key="target_design_preview_target_type",
                help="Optional route hint for documentation review.",
            )
            expression_purpose = st.text_input(
                "Expression purpose",
                value="",
                key="target_design_preview_expression_purpose",
                help="Optional note kept in the preview only.",
            )
        with input_cols[1]:
            host_category = st.selectbox(
                "Host category",
                options=HOST_CATEGORY_OPTIONS,
                key="target_design_preview_host_category",
                help="Optional host context for documentation review.",
            )
            specific_host = st.text_input(
                "Specific host",
                value="",
                key="target_design_preview_specific_host",
                help="Optional host label for source confirmation.",
            )

        route_result = target_design_router.route_target_design(
            target_name=target_name,
            target_type=target_type,
            host_category=host_category,
            specific_host=specific_host,
            expression_purpose=expression_purpose,
        )
        preview = target_design_router_preview.build_target_design_preview(route_result)

        target_summary = preview["target_summary"]
        route_summary = preview["design_route_summary"]
        template_summary = preview["construct_template_summary"]
        render_compact_summary_cards(
            [
                ("Target class", _text(target_summary.get("target_class"), "unresolved_target"), None),
                ("Design route", _text(route_summary.get("design_route"), "needs_target_clarification"), None),
                ("Support status", _text(preview.get("support_status"), "unresolved"), None),
                ("Review label", _text(preview.get("readiness_label"), "Draft only"), "manual review label only"),
            ]
        )
        st.caption(TARGET_PREVIEW_SCAN_COPY)

        overview_tab, structure_tab, review_tab, readback_tab = st.tabs(
            ["Overview", "Draft structure", "Review checklist", "Markdown readback"]
        )
        with overview_tab:
            render_subsection_heading("Target context")
            st.dataframe(
                pd.DataFrame(_field_value_rows(target_summary, ["target_label", "aliases", "notes"])),
                hide_index=True,
                use_container_width=True,
            )

            render_subsection_heading("Route summary")
            st.dataframe(
                pd.DataFrame(
                    _field_value_rows(
                        route_summary,
                        ["design_route", "route_label", "review_status", "support_status"],
                    )
                ),
                hide_index=True,
                use_container_width=True,
            )

        with structure_tab:
            render_subsection_heading("Construct draft template")
            st.dataframe(
                pd.DataFrame(
                    _field_value_rows(
                        template_summary,
                        ["template_id", "template_label", "description", "structure"],
                    )
                ),
                hide_index=True,
                use_container_width=True,
            )
            _render_preview_table("Gene slots", preview["gene_slots_table"])
            _render_preview_table("Cassette slots", preview["cassette_slots_table"])
            _render_preview_table("Required parts", preview["required_parts_table"])

        with review_tab:
            st.caption(TARGET_PREVIEW_REVIEW_HELP_COPY)
            _render_preview_table("Missing fields", preview["missing_fields_table"])
            _render_preview_table("Source requirements", preview["source_requirements_table"])

            render_subsection_heading("Review notes")
            for note in preview["review_notes"]:
                st.caption(_text(note))
            st.caption(_text(preview.get("boundary_note")))

        with readback_tab:
            st.caption(TARGET_PREVIEW_READBACK_COPY)
            st.code(
                target_design_router_preview_report.format_target_design_preview_markdown(preview),
                language="markdown",
            )


def _construct_lookup() -> list[dict[str, str]]:
    rows = repo.list_construct_profiles()
    return [
        {
            "construct_id": _text(row.get("construct_id")),
            "label": f"{_text(row.get('construct_label'), presenter.DEFAULT_CONSTRUCT_LABEL)} / {_text(row.get('construct_id'))}",
        }
        for row in rows
        if _text(row.get("construct_id"))
    ]


def _cassette_lookup(construct_id: str) -> list[dict[str, str]]:
    return [
        {
            "cassette_id": _text(row.get("cassette_id")),
            "label": f"{_text(row.get('cassette_label'), presenter.DEFAULT_CASSETTE_LABEL)} / {_text(row.get('cassette_id'))}",
        }
        for row in repo.list_construct_cassettes(construct_id)
        if _text(row.get("cassette_id"))
    ]


def _select_active_construct(constructs: list[dict[str, str]]) -> str:
    current = _text(st.session_state.get(SELECTED_CONSTRUCT_KEY))
    valid_ids = [row["construct_id"] for row in constructs]
    if current not in valid_ids:
        current = valid_ids[0] if valid_ids else ""
        if current:
            st.session_state[SELECTED_CONSTRUCT_KEY] = current
        else:
            st.session_state.pop(SELECTED_CONSTRUCT_KEY, None)
    return current


def _save_construct_form(defaults: dict[str, object]) -> None:
    render_section_heading("Create Construct Draft")
    with st.form("expression_construct_create_form"):
        construct_label = st.text_input(
            "Construct label",
            value=_text(defaults.get("construct_label")),
            key="expression_construct_create_label",
        )
        construct_type = st.text_input(
            "Construct type",
            value=_text(defaults.get("construct_type")),
            key="expression_construct_create_type",
        )
        host_context_note = st.text_area(
            "Organism / context note",
            value="",
            key="expression_construct_create_host_context",
        )
        source_reference = st.text_input(
            "Source / provenance note",
            value="",
            key="expression_construct_create_source",
        )
        review_status = st.text_input(
            "Curation status",
            value=_text(defaults.get("review_status")),
            key="expression_construct_create_status",
        )
        review_note = st.text_area(
            "Review note",
            value="",
            key="expression_construct_create_review_note",
        )
        submitted = st.form_submit_button("Create construct draft", key="expression_construct_create_submit")
    if submitted:
        created = repo.create_construct_profile(
            construct_label=construct_label,
            construct_type=construct_type,
            host_context_note=host_context_note,
            source_reference=source_reference,
            provenance_note=source_reference,
            review_status=review_status,
            documentation_scope_note=review_note,
        )
        construct_id = _text(created.get("construct_id"))
        if construct_id:
            st.session_state[SELECTED_CONSTRUCT_KEY] = construct_id
            st.success("Construct draft saved to the local documentation workspace.")
            st.rerun()


def _edit_construct_form(active_construct_id: str, defaults: dict[str, object]) -> None:
    render_section_heading("Edit Construct Metadata")
    if not active_construct_id:
        st.info("Select or create a construct draft to edit its metadata.")
        return
    profile = repo.get_construct_profile(active_construct_id)
    if not profile:
        st.info("The selected construct draft could not be loaded from the local documentation workspace.")
        return
    with st.form("expression_construct_edit_form"):
        construct_label = st.text_input(
            "Construct label",
            value=_text(profile.get("construct_label"), _text(defaults.get("construct_label"))),
            key="expression_construct_edit_label",
        )
        construct_type = st.text_input(
            "Construct type",
            value=_text(profile.get("construct_type"), _text(defaults.get("construct_type"))),
            key="expression_construct_edit_type",
        )
        host_context_note = st.text_area(
            "Organism / context note",
            value=_text(profile.get("host_context_note")),
            key="expression_construct_edit_host_context",
        )
        source_reference = st.text_input(
            "Source / provenance note",
            value=_text(profile.get("source_reference")),
            key="expression_construct_edit_source",
        )
        review_status = st.text_input(
            "Curation status",
            value=_text(profile.get("review_status"), _text(defaults.get("review_status"))),
            key="expression_construct_edit_status",
        )
        review_note = st.text_area(
            "Review note",
            value=_text(profile.get("documentation_scope_note")),
            key="expression_construct_edit_review_note",
        )
        submitted = st.form_submit_button("Save construct metadata", key="expression_construct_edit_submit")
    if submitted:
        repo.update_construct_profile(
            active_construct_id,
            construct_label=construct_label,
            construct_type=construct_type,
            host_context_note=host_context_note,
            source_reference=source_reference,
            provenance_note=source_reference,
            review_status=review_status,
            documentation_scope_note=review_note,
        )
        st.success("Construct metadata updated in the local documentation workspace.")
        st.rerun()


def _add_cassette_form(active_construct_id: str, defaults: dict[str, object]) -> None:
    render_section_heading("Add Expression Cassette")
    if not active_construct_id:
        st.info("Create a construct draft before adding cassette rows.")
        return
    with st.form("expression_construct_add_cassette_form"):
        cassette_label = st.text_input(
            "Cassette label",
            value=_text(defaults.get("cassette_label")),
            key="expression_construct_add_cassette_label",
        )
        cassette_order = st.number_input("Cassette order", min_value=0, value=1, key="expression_construct_add_cassette_order")
        cassette_role = st.text_input(
            "Cassette type",
            value=_text(defaults.get("cassette_role")),
            key="expression_construct_add_cassette_role",
        )
        source_reference = st.text_input(
            "Source / provenance note",
            value="",
            key="expression_construct_add_cassette_source",
        )
        review_note = st.text_area(
            "Review note",
            value="",
            key="expression_construct_add_cassette_review_note",
        )
        submitted = st.form_submit_button("Add expression cassette", key="expression_construct_add_cassette_submit")
    if submitted:
        repo.create_construct_cassette(
            active_construct_id,
            cassette_label=cassette_label,
            cassette_role=cassette_role,
            cassette_order=int(cassette_order),
            source_reference=source_reference,
            provenance_note=review_note,
        )
        st.success("Cassette row saved to the local documentation workspace.")
        st.rerun()


def _add_cassette_part_form(active_construct_id: str) -> None:
    render_section_heading("Add Cassette Part Row")
    if not active_construct_id:
        st.info("Create a construct draft before adding cassette part rows.")
        return
    cassette_options = _cassette_lookup(active_construct_id)
    if not cassette_options:
        st.info("Add an expression cassette before adding cassette part rows.")
        return
    with st.form("expression_construct_add_part_form"):
        selected_label = st.selectbox(
            "Cassette id or selected cassette",
            options=[row["label"] for row in cassette_options],
            key="expression_construct_part_cassette",
        )
        selected_cassette_id = next(
            (row["cassette_id"] for row in cassette_options if row["label"] == selected_label),
            "",
        )
        part_order = st.number_input("Part order", min_value=0, value=1, key="expression_construct_part_order")
        part_role = st.selectbox("Part role", options=list(repo.PART_ROLE_TERMS), key="expression_construct_part_role")
        part_label = st.text_input("Part label", value="", key="expression_construct_part_label")
        attach_catalog_context = part_role == "promoter" or st.checkbox(
            "Attach Component Library promoter asset source context",
            value=False,
            key="expression_construct_part_attach_promoter_context",
        )
        selected_source = {}
        if attach_catalog_context:
            promoter_options = _promoter_source_options()
            if promoter_options:
                selected_promoter_label = st.selectbox(
                    "Component Library promoter asset source record",
                    options=["No catalog source record"] + [row["select_label"] for row in promoter_options],
                    key="expression_construct_part_promoter_source",
                )
                selected_source = next(
                    (row for row in promoter_options if row["select_label"] == selected_promoter_label),
                    {},
                )
            else:
                st.info(
                    f"No Component Library promoter asset rows are available. {presenter.PROMOTER_SOURCE_LINK_EMPTY_COPY}"
                )
        source_reference = st.text_input("Source / provenance note", value="", key="expression_construct_part_source")
        review_note = st.text_area("Review note", value="", key="expression_construct_part_review")
        submitted = st.form_submit_button("Add cassette part row", key="expression_construct_add_part_submit")
    if submitted:
        repo.add_construct_cassette_part(
            selected_cassette_id,
            part_order=int(part_order),
            part_role=part_role,
            part_label=part_label,
            source_reference=source_reference,
            source_catalog=presenter.PLANT_PROMOTER_CATALOG_LABEL if selected_source else "",
            source_record_id=_text(selected_source.get("record_id")) if selected_source else "",
            source_record_label=_text(selected_source.get("record_label")) if selected_source else "",
            evidence_context_note=_text(selected_source.get("context_note")) if selected_source else "",
            provenance_note=review_note,
        )
        st.success("Cassette part row saved to the local documentation workspace.")
        st.rerun()


def _add_gene_link_form(active_construct_id: str) -> None:
    render_section_heading("Add Gene Link")
    if not active_construct_id:
        st.info("Create a construct draft before adding linked gene rows.")
        return
    with st.form("expression_construct_add_gene_form"):
        gene_label = st.text_input("Gene label", value="", key="expression_construct_gene_label")
        gene_reference = st.text_input("Gene reference", value="", key="expression_construct_gene_reference")
        source_reference = st.text_input("Source / provenance note", value="", key="expression_construct_gene_source")
        review_note = st.text_area("Review note", value="", key="expression_construct_gene_review")
        submitted = st.form_submit_button("Add gene link", key="expression_construct_add_gene_submit")
    if submitted:
        repo.add_construct_gene_link(
            active_construct_id,
            gene_label=gene_label,
            gene_reference=gene_reference,
            source_reference=source_reference,
            provenance_note=review_note,
        )
        st.success("Gene link saved to the local documentation workspace.")
        st.rerun()


def _add_pathway_link_form(active_construct_id: str) -> None:
    render_section_heading("Add Pathway Step Link")
    if not active_construct_id:
        st.info("Create a construct draft before adding linked pathway step rows.")
        return
    with st.form("expression_construct_add_pathway_form"):
        pathway_step_id = st.text_input(
            "Pathway project / step reference",
            value="",
            key="expression_construct_pathway_reference",
        )
        pathway_step_label = st.text_input("Step label", value="", key="expression_construct_pathway_label")
        source_reference = st.text_input("Link note", value="", key="expression_construct_pathway_source")
        review_note = st.text_area("Review note", value="", key="expression_construct_pathway_review")
        submitted = st.form_submit_button("Add pathway step link", key="expression_construct_add_pathway_submit")
    if submitted:
        repo.add_construct_pathway_step_link(
            active_construct_id,
            pathway_step_id=pathway_step_id,
            pathway_step_label=pathway_step_label,
            source_reference=source_reference,
            provenance_note=review_note,
        )
        st.success("Pathway step link saved to the local documentation workspace.")
        st.rerun()


def _add_project_link_form(active_construct_id: str) -> None:
    render_section_heading("Add Project Link")
    if not active_construct_id:
        st.info("Create or select a construct draft before adding project-level construct links.")
        return
    with st.form("expression_construct_add_project_link_form"):
        project_id = st.text_input(
            "Pathway project id / reference",
            value="",
            key="expression_construct_project_link_project_id",
        )
        link_label = st.text_input(
            "Project link label",
            value="",
            key="expression_construct_project_link_label",
        )
        link_note = st.text_area(
            "Project link note",
            value="",
            key="expression_construct_project_link_note",
        )
        source_context = st.text_input(
            "Source context",
            value="Expression Constructs manual project link",
            key="expression_construct_project_link_source_context",
        )
        curation_status = st.text_input(
            "Curation status",
            value="documentation review pending",
            key="expression_construct_project_link_curation_status",
        )
        review_note = st.text_area(
            "Review note",
            value="",
            key="expression_construct_project_link_review_note",
        )
        submitted = st.form_submit_button("Add project link", key="expression_construct_add_project_link_submit")
    if submitted:
        linked = repo.create_construct_project_link(
            project_id=project_id,
            construct_id=active_construct_id,
            link_label=link_label,
            link_note=link_note,
            source_context=source_context,
            curation_status=curation_status,
            review_note=review_note,
        )
        if linked:
            st.success("Project-level construct link saved as a documentation reference.")
            st.rerun()
        else:
            st.warning("Project-level construct link was not saved. Provide a project id and select an existing construct draft.")


def render() -> None:
    inject_tool_typography_css()
    render_tool_header(PAGE_TITLE, PAGE_SUBTITLE)
    render_boundary_note(BOUNDARY_COPY)
    render_help_text(presenter.WORKFLOW_COPY)
    render_tool_intro("Documentation-only construct drafts", INTRO_COPY)
    render_help_text(FILTER_HELP_COPY)
    _render_target_design_preview_panel()

    construct_options = _construct_lookup()
    active_construct_id = _select_active_construct(construct_options)
    left_col, right_col = st.columns(2)
    with left_col:
        default_view_model = _sanitize_view_model(presenter.build_expression_construct_presenter(construct_id=active_construct_id))
        _save_construct_form(default_view_model["draft_defaults"])
        _edit_construct_form(active_construct_id, default_view_model["draft_defaults"])
        _add_cassette_form(active_construct_id, default_view_model["draft_defaults"])
    with right_col:
        _add_cassette_part_form(active_construct_id)
        _add_gene_link_form(active_construct_id)
        _add_pathway_link_form(active_construct_id)
        _add_project_link_form(active_construct_id)

    raw = presenter.build_expression_construct_presenter(
        construct_id=active_construct_id,
        step2_component_context=_current_step2_component_context_readback(),
    )
    view_model = _sanitize_view_model(raw)
    summary = view_model["summary_counts"]

    render_section_heading("Current Construct Preview")
    if construct_options:
        selected_labels = [row["label"] for row in construct_options]
        current_label = next((row["label"] for row in construct_options if row["construct_id"] == active_construct_id), selected_labels[0])
        selected_label = st.selectbox(
            "Current construct draft",
            options=selected_labels,
            index=selected_labels.index(current_label) if current_label in selected_labels else 0,
            key="expression_construct_selected_construct_label",
        )
        selected_construct_id = next((row["construct_id"] for row in construct_options if row["label"] == selected_label), active_construct_id)
        if selected_construct_id != active_construct_id:
            st.session_state[SELECTED_CONSTRUCT_KEY] = selected_construct_id
            st.rerun()
    else:
        st.info(_text(view_model["empty_states"].get("constructs")))

    render_compact_summary_cards(
        [
            ("Construct profiles", str(summary["construct_profile_count"]), None),
            ("Expression cassettes", str(summary["cassette_count"]), None),
            ("Cassette part rows", str(summary["cassette_part_count"]), None),
            ("Linked genes", str(summary["gene_link_count"]), None),
            ("Linked pathway steps", str(summary["pathway_step_link_count"]), None),
            ("Project links", str(summary["project_link_count"]), None),
            ("Rows needing review", str(summary["review_gap_count"]), None),
        ]
    )
    st.caption(_text(view_model.get("boundary_copy"), presenter.BOUNDARY_COPY))

    profile_rows = _row_list(view_model.get("construct_profile_rows"))
    cassette_rows = _row_list(view_model.get("cassette_rows"))
    part_rows = _row_list(view_model.get("cassette_part_rows"))
    component_rows = _row_list(view_model.get("construct_component_rows"))
    component_review_summary = view_model["construct_component_review_summary"]
    component_gap_queue = _row_list(view_model.get("construct_component_gap_queue"))
    step2_component_context_readback = view_model["step2_component_context_readback"]
    gene_rows = _row_list(view_model.get("linked_gene_rows"))
    pathway_rows = _row_list(view_model.get("linked_pathway_step_rows"))
    project_link_rows = _row_list(view_model.get("project_link_rows"))
    gap_rows = _row_list(view_model.get("review_gap_rows"))

    filter_cols = st.columns(4)
    with filter_cols[0]:
        selected_type = _selected_value("Construct type", _construct_type_options(profile_rows), "expression_construct_type")
    with filter_cols[1]:
        selected_status = _selected_value("Curation status", _construct_status_options(profile_rows), "expression_construct_status")
    with filter_cols[2]:
        selected_cassette = _selected_value(
            "Cassette label",
            presenter.cassette_label_options(cassette_rows),
            "expression_construct_cassette",
        )
    with filter_cols[3]:
        selected_pathway = _selected_value(
            "Pathway step reference",
            presenter.pathway_reference_options(pathway_rows),
            "expression_construct_pathway",
        )

    profile_rows, cassette_rows, part_rows, gene_rows, pathway_rows, gap_rows = presenter.filter_expression_construct_display_rows(
        profile_rows,
        cassette_rows,
        part_rows,
        gene_rows,
        pathway_rows,
        gap_rows,
        construct_type=selected_type,
        construct_status=selected_status,
        cassette_label=selected_cassette,
        pathway_ref=selected_pathway,
    )
    if selected_cassette != "all":
        component_rows = [
            row for row in component_rows if _text(row.get("cassette_label"), presenter.DEFAULT_CASSETTE_LABEL) == selected_cassette
        ]
        component_gap_queue = [
            row
            for row in component_gap_queue
            if _text(row.get("Cassette label"), presenter.DEFAULT_CASSETTE_LABEL) == selected_cassette
        ]
        component_review_summary = presenter.build_construct_component_review_summary(
            component_rows,
            component_gap_queue,
        )

    if not profile_rows:
        _render_cassette_slot_preview(
            profile_rows=profile_rows,
            cassette_rows=cassette_rows,
            part_rows=part_rows,
            component_rows=component_rows,
            step2_component_context_readback=step2_component_context_readback,
            gene_rows=gene_rows,
            gap_rows=gap_rows,
        )
        st.info(_text(view_model["empty_states"].get("constructs")))
        return

    if not cassette_rows:
        st.info(_text(view_model["empty_states"].get("cassettes")))
    if not part_rows:
        st.caption(_text(view_model["empty_states"].get("parts")))
    if not component_rows:
        st.caption(
            "No component readback rows are available for the selected construct/cassette filter yet. "
            "Clear filters or add cassette part rows before reviewing source/provenance context."
        )
    if not gene_rows:
        st.caption("No linked gene rows are recorded for the selected construct draft yet.")
    if not pathway_rows:
        st.caption("No linked pathway step rows are recorded for the selected construct draft yet.")
    if not project_link_rows:
        st.caption(_text(view_model["empty_states"].get("project_links")))

    render_section_heading("Construct profiles")
    st.dataframe(pd.DataFrame(presenter.construct_profile_table_rows(profile_rows), columns=TABLE_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Expression cassettes")
    st.dataframe(pd.DataFrame(presenter.cassette_table_rows(cassette_rows), columns=CASSETTE_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Cassette parts")
    st.dataframe(pd.DataFrame(presenter.cassette_part_table_rows(part_rows), columns=PART_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Construct component readback")
    st.caption(COMPONENT_READBACK_COPY)
    st.dataframe(
        pd.DataFrame(presenter.construct_component_table_rows(component_rows), columns=COMPONENT_COLUMNS),
        hide_index=True,
        use_container_width=True,
    )
    _render_cassette_slot_preview(
        profile_rows=profile_rows,
        cassette_rows=cassette_rows,
        part_rows=part_rows,
        component_rows=component_rows,
        step2_component_context_readback=step2_component_context_readback,
        gene_rows=gene_rows,
        gap_rows=gap_rows,
    )
    _render_step2_component_context_readback(step2_component_context_readback)
    _render_component_review_action_cue(component_gap_queue)
    render_section_heading("Construct review summary")
    st.caption(COMPONENT_REVIEW_SUMMARY_COPY)
    render_compact_summary_cards(
        [
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["total_component_rows"],
                str(component_review_summary["total_component_rows"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_source_reference_context"],
                str(component_review_summary["rows_with_source_reference_context"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_missing_source_reference_context"],
                str(component_review_summary["rows_missing_source_reference_context"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_sequence_availability_note"],
                str(component_review_summary["rows_with_sequence_availability_note"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_review_metadata_status"],
                str(component_review_summary["rows_with_review_metadata_status"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_review_note"],
                str(component_review_summary["rows_with_review_note"]),
                None,
            ),
            (
                presenter.COMPONENT_REVIEW_SUMMARY_LABELS["rows_needing_manual_follow_up"],
                str(component_review_summary["rows_needing_manual_follow_up"]),
                None,
            ),
        ]
    )
    render_section_heading("Manual follow-up queue")
    st.caption(COMPONENT_FOLLOW_UP_QUEUE_COPY)
    if not component_gap_queue:
        st.info(
            "No manual documentation follow-up rows are visible for the current construct/cassette filter. "
            "Clear filters or review construct metadata, cassette parts, linked genes, pathway links, and review gaps "
            "if more source/provenance context is needed."
        )
    else:
        st.caption(
            "Start with rows whose follow-up type mentions missing source/reference context, missing provenance context, "
            "role-label review, duplicate-label review, or missing review note. Use the manual review detail before "
            "editing local draft records."
        )
    st.dataframe(
        _component_follow_up_queue_frame(component_gap_queue),
        hide_index=True,
        use_container_width=True,
    )
    render_section_heading("Linked genes")
    st.dataframe(pd.DataFrame(presenter.linked_gene_table_rows(gene_rows), columns=GENE_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Linked pathway steps")
    st.dataframe(pd.DataFrame(presenter.linked_pathway_step_table_rows(pathway_rows), columns=PATHWAY_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Project links")
    st.dataframe(pd.DataFrame(presenter.project_link_table_rows(project_link_rows), columns=PROJECT_LINK_COLUMNS), hide_index=True, use_container_width=True)
    render_section_heading("Review gaps")
    st.caption(REVIEW_GAP_COPY)
    st.dataframe(pd.DataFrame(presenter.review_gap_table_rows(gap_rows), columns=GAP_COLUMNS), hide_index=True, use_container_width=True)
