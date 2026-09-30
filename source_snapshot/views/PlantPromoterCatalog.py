from __future__ import annotations

import pandas as pd
import streamlit as st

from services import catalog_reference_basket_service as basket_service
from services import plant_promoter_catalog_presenter as presenter
from services import plant_promoter_evidence_gap_review_queue as evidence_gap_queue
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services import plant_promoter_catalog_workspace_presenter as workspace_presenter
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_tool_header,
    render_tool_intro,
)


PAGE_TITLE = "Promoter Assets - Plant Domain"
PAGE_SUBTITLE = (
    "Component Library detail surface for plant promoter profile rows, tissue-context evidence rows, and motif notes."
)
BOUNDARY_COPY = (
    "Read-only documentation detail surface for Plant Promoter Catalog profile rows and child evidence rows. "
    "This page does not provide selection advice, record ordering, behavior forecasts, source verification, "
    "or wet-lab use guidance."
)
INTRO_COPY = (
    "Browse documentation-only plant promoter profile rows, tissue-context evidence rows, and review notes. "
    "Source/review fields are manual review context, not selection advice or biological approval."
)
FILTER_HELP_COPY = (
    "Filters narrow the local documentation view only. Missing tissue context and missing source database labels stay visible "
    "as recorded review gaps rather than hidden assumptions."
)

TABLE_COLUMNS = [
    "Promoter / part label",
    "Plant clade",
    "Species",
    "Tissue context",
    "Evidence type",
    "Source context",
    "Curation status",
    "Review note",
]
CONTEXT_READBACK_COLUMNS = [
    "Promoter / catalog label",
    "Species or clade context",
    "Tissue evidence context",
    "Source/review metadata",
    "Metadata gap",
]
PROFILE_COLUMNS = [
    "Promoter / part label",
    "Alias / locus",
    "Plant clade",
    "Species",
    "Promoter type",
    "Sequence availability",
    "Tissue contexts",
    "Evidence rows",
    "Motif rows",
]
DETAIL_EVIDENCE_COLUMNS = [
    "Tissue context",
    "Plant ontology ID",
    "Development stage",
    "Expression context label",
    "Evidence type",
    "Evidence summary",
    "Source context label",
    "Publication/citation context",
    "Curation status",
    "Review note",
]
DETAIL_MOTIF_COLUMNS = [
    "Motif",
    "Motif source context",
    "Accession",
    "Sequence / consensus",
    "Position note",
    "Function note",
    "Evidence note",
]
SOURCE_REVIEW_COLUMNS = ["Metadata context", "Recorded value"]
SOURCE_REVIEW_LABELS = {
    "Catalog identity": "Catalog record identifier",
    "Source labels": "Source context labels",
    "Motif sources": "Motif source context",
    "Review status labels": "Curation status labels",
    "Review notes": "Review note context",
    "Missing metadata count": "Metadata gap count",
}
REVIEW_NEEDED_COLUMNS = [
    "Promoter / part label",
    "Tissue context",
    "Curation status",
    "Review-needed source/review context",
]
HOST_TISSUE_READBACK_COLUMNS = [
    "Species context",
    "Clade context",
    "Promoter records",
    "Tissue evidence metadata",
    "Source context metadata",
    "Review gaps",
]
EVIDENCE_GAP_QUEUE_COLUMNS = [
    "Queue item ID",
    "Promoter / part label",
    "Category",
    "Issue",
    "Human follow-up",
    "Source context",
]


def _text(value: object, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _option_values(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [value for value in (_text(item) for item in raw) if value]


def _row_list(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _text_int_map(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    rows: dict[str, int] = {}
    for key, value in raw.items():
        label = _text(key)
        if not label:
            continue
        try:
            rows[label] = int(value or 0)
        except (TypeError, ValueError):
            rows[label] = 0
    return rows


def _sanitize_view_model(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raw = {}

    summary = raw.get("summary_counts")
    if not isinstance(summary, dict):
        summary = {}

    return {
        "summary_counts": {
            "profile_count": int(summary.get("profile_count") or 0),
            "tissue_evidence_count": int(summary.get("tissue_evidence_count") or 0),
            "motif_annotation_count": int(summary.get("motif_annotation_count") or 0),
            "rows_needing_review_count": int(summary.get("rows_needing_review_count") or 0),
            "source_database_count": int(summary.get("source_database_count") or 0),
            "linked_catalog_reference_count": int(summary.get("linked_catalog_reference_count") or 0),
        },
        "available_plant_clades": _option_values(raw.get("available_plant_clades")),
        "available_species": _option_values(raw.get("available_species")),
        "available_tissue_contexts": _option_values(raw.get("available_tissue_contexts")),
        "available_evidence_types": _option_values(raw.get("available_evidence_types")),
        "available_curation_statuses": _option_values(raw.get("available_curation_statuses")),
        "tissue_context_evidence_summary": _text_int_map(raw.get("tissue_context_evidence_summary")),
        "rows_needing_review": _row_list(raw.get("rows_needing_review")),
        "source_evidence_labels": _option_values(raw.get("source_evidence_labels")),
        "profile_rows": _row_list(raw.get("profile_rows")),
        "evidence_rows": _row_list(raw.get("evidence_rows")),
        "motif_preview_rows": _row_list(raw.get("motif_preview_rows")),
        "context_readback_rows": _row_list(raw.get("context_readback_rows")),
        "boundary_note": _text(raw.get("boundary_note"), presenter.BOUNDARY_NOTE),
        "documentation_only_context_note": _text(
            raw.get("documentation_only_context_note"),
            presenter.READBACK_BOUNDARY_NOTE,
        ),
        "catalog_source": _text(raw.get("catalog_source")),
        "catalog_status_label": _text(raw.get("catalog_status_label")),
        "documentation_status_label": _text(raw.get("documentation_status_label")),
        "persistent_profile_count": int(raw.get("persistent_profile_count") or 0),
        "seed_profile_count": int(raw.get("seed_profile_count") or 0),
        "represented_source_database_labels": _option_values(raw.get("represented_source_database_labels")),
        "linked_catalog_reference_labels": _option_values(raw.get("linked_catalog_reference_labels")),
        "represented_profile_ids": _option_values(raw.get("represented_profile_ids")),
        "seed_metadata": raw.get("seed_metadata") if isinstance(raw.get("seed_metadata"), dict) else {},
        "seed_warnings": _option_values(raw.get("seed_warnings")),
    }


def _build_table_rows(evidence_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Promoter / part label": _text(row.get("promoter_label"), "Unknown promoter record"),
            "Plant clade": _text(row.get("plant_clade"), presenter.NO_CLADE_LABEL),
            "Species": _text(row.get("species_label"), presenter.NO_SPECIES_LABEL),
            "Tissue context": _text(row.get("tissue_context"), presenter.NO_TISSUE_LABEL),
            "Evidence type": _text(row.get("evidence_type"), presenter.NO_EVIDENCE_TYPE_LABEL),
            "Source context": _text(row.get("source_database"), presenter.NO_SOURCE_LABEL),
            "Curation status": _text(row.get("curation_status"), presenter.NO_CURATION_STATUS_LABEL),
            "Review note": _text(row.get("review_note"), "No review note recorded"),
        }
        for row in evidence_rows
    ]


def _build_context_readback_rows(context_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Promoter / catalog label": _text(row.get("catalog_context"), "Unknown promoter record"),
            "Species or clade context": _text(
                row.get("species_or_clade_context"),
                f"{presenter.NO_SPECIES_LABEL}; {presenter.NO_CLADE_LABEL}",
            ),
            "Tissue evidence context": _text(
                row.get("tissue_evidence_context"),
                presenter.NO_TISSUE_LABEL,
            ),
            "Source/review metadata": _text(
                row.get("source_review_metadata"),
                "No source context or review metadata recorded",
            ),
            "Metadata gap": _text(
                row.get("metadata_gap"),
                "Metadata gap remains visible for documentation review",
            ),
        }
        for row in context_rows
    ]


def _build_motif_rows(motif_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Promoter / part label": _text(row.get("promoter_label"), "Unknown promoter record"),
            "Motif": _text(row.get("motif_name"), "Unnamed motif note"),
            "Motif source context": _text(row.get("motif_source"), presenter.NO_SOURCE_LABEL),
            "Accession": _text(row.get("motif_accession"), "No source accession recorded"),
            "Evidence note": _text(row.get("evidence_note"), "No motif evidence note recorded"),
        }
        for row in motif_rows
    ]


def _build_profile_table_rows(detail_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Promoter / part label": _text(row.get("promoter_label"), "Unknown promoter record"),
            "Alias / locus": _text(row.get("alias"), "No alias or locus recorded"),
            "Plant clade": _text(row.get("plant_clade"), presenter.NO_CLADE_LABEL),
            "Species": _text(row.get("species_label"), presenter.NO_SPECIES_LABEL),
            "Promoter type": _text(row.get("promoter_type"), "No promoter type recorded"),
            "Sequence availability": _text(row.get("sequence_availability"), "No sequence availability note recorded"),
            "Tissue contexts": str(row.get("tissue_context_count") or 0),
            "Evidence rows": str(row.get("evidence_row_count") or 0),
            "Motif rows": str(row.get("motif_annotation_count") or 0),
        }
        for row in detail_rows
    ]


def _build_detail_evidence_rows(evidence_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Tissue context": _text(row.get("tissue_context"), presenter.NO_TISSUE_LABEL),
            "Plant ontology ID": _text(row.get("plant_ontology_id"), "No plant ontology id recorded"),
            "Development stage": _text(row.get("development_stage"), "No development stage recorded"),
            "Expression context label": _text(row.get("expression_context_label"), "No expression context label recorded"),
            "Evidence type": _text(row.get("evidence_type"), presenter.NO_EVIDENCE_TYPE_LABEL),
            "Evidence summary": _text(row.get("evidence_summary"), "No evidence summary recorded"),
            "Source context label": _text(row.get("source_label"), presenter.NO_SOURCE_LABEL),
            "Publication/citation context": _text(row.get("publication_reference"), "No publication reference recorded"),
            "Curation status": _text(row.get("curation_status"), presenter.NO_CURATION_STATUS_LABEL),
            "Review note": _text(row.get("review_note"), "No review note recorded"),
        }
        for row in evidence_rows
    ]


def _build_detail_motif_rows(motif_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Motif": _text(row.get("motif_name"), "Unnamed motif note"),
            "Motif source context": _text(row.get("motif_source"), presenter.NO_SOURCE_LABEL),
            "Accession": _text(row.get("motif_accession"), "No motif accession recorded"),
            "Sequence / consensus": _text(row.get("motif_sequence_or_consensus"), "No motif sequence note recorded"),
            "Position note": _text(row.get("motif_position_note"), "No motif position note recorded"),
            "Function note": _text(row.get("associated_function_note"), "No associated function note recorded"),
            "Evidence note": _text(row.get("evidence_note"), "No motif evidence note recorded"),
        }
        for row in motif_rows
    ]


def _build_source_review_rows(source_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Metadata context": SOURCE_REVIEW_LABELS.get(
                _text(row.get("metadata_group")),
                _text(row.get("metadata_group"), "Metadata context"),
            ),
            "Recorded value": _text(row.get("metadata_value"), "Not recorded"),
        }
        for row in source_rows
    ]


def _build_review_needed_rows(review_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Promoter / part label": _text(
                row.get("display_name"),
                _text(row.get("part_id"), "Unknown promoter record"),
            ),
            "Tissue context": _text(row.get("tissue_context"), presenter.NO_TISSUE_LABEL),
            "Curation status": _text(row.get("curation_status"), presenter.NO_CURATION_STATUS_LABEL),
            "Review-needed source/review context": _text(
                row.get("review_note"),
                "No review note recorded; metadata gap remains visible for human review.",
            ),
        }
        for row in review_rows
    ]


def _build_evidence_gap_queue_rows(queue_rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [
        {
            "Queue item ID": _text(row.get("queue_item_id"), "untracked-gap"),
            "Promoter / part label": _text(row.get("promoter_label"), "Unknown promoter record"),
            "Category": _text(row.get("category"), "documentation_follow_up"),
            "Issue": _text(row.get("issue"), "Documentation follow-up remains visible."),
            "Human follow-up": _text(
                row.get("human_follow_up"),
                "Use for documentation review and human curation only.",
            ),
            "Source context": _text(row.get("source_context"), presenter.NO_SOURCE_LABEL),
        }
        for row in queue_rows
    ]


def _readback_bucket() -> dict[str, object]:
    return {"promoters": set(), "tissues": set(), "source_contexts": set(), "review_gap_count": 0}


def _build_host_tissue_readback_rows(
    profile_rows: list[dict[str, object]],
    evidence_rows: list[dict[str, object]],
    review_rows: list[dict[str, object]],
) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for profile in profile_rows:
        clade = _text(profile.get("plant_clade"), presenter.NO_CLADE_LABEL)
        species = _text(profile.get("species_label"), presenter.NO_SPECIES_LABEL)
        bucket = grouped.setdefault((species, clade), _readback_bucket())
        promoter = _text(profile.get("display_name"), _text(profile.get("part_id"), "Unknown promoter record"))
        bucket["promoters"].add(promoter)

    for evidence in evidence_rows:
        clade = _text(evidence.get("plant_clade"), presenter.NO_CLADE_LABEL)
        species = _text(evidence.get("species_label"), presenter.NO_SPECIES_LABEL)
        bucket = grouped.setdefault((species, clade), _readback_bucket())
        bucket["promoters"].add(_text(evidence.get("promoter_label"), "Unknown promoter record"))
        bucket["tissues"].add(_text(evidence.get("tissue_context"), presenter.NO_TISSUE_LABEL))
        bucket["source_contexts"].add(_text(evidence.get("source_database"), presenter.NO_SOURCE_LABEL))

    for row in review_rows:
        promoter = _text(row.get("display_name"), _text(row.get("part_id")))
        tissue = _text(row.get("tissue_context"), presenter.NO_TISSUE_LABEL)
        for bucket in grouped.values():
            if promoter and promoter not in bucket["promoters"]:
                continue
            if tissue and tissue not in bucket["tissues"]:
                continue
            bucket["review_gap_count"] = int(bucket["review_gap_count"] or 0) + 1

    rows: list[dict[str, str]] = []
    for (species, clade), bucket in sorted(
        grouped.items(),
        key=lambda item: (item[0][0].casefold(), item[0][1].casefold()),
    ):
        promoters = sorted(bucket["promoters"], key=str.casefold)
        tissues = sorted(bucket["tissues"], key=str.casefold)
        source_contexts = sorted(bucket["source_contexts"], key=str.casefold)
        review_gap_count = int(bucket["review_gap_count"] or 0)
        rows.append(
            {
                "Species context": species,
                "Clade context": clade,
                "Promoter records": str(len(promoters)),
                "Tissue evidence metadata": "; ".join(tissues) if tissues else "No tissue evidence rows visible",
                "Source context metadata": "; ".join(source_contexts)
                if source_contexts
                else "No source context metadata rows visible",
                "Review gaps": (
                    f"{review_gap_count} review-needed rows"
                    if review_gap_count
                    else "No review-needed rows visible"
                ),
            }
        )
    return rows


def _format_count_summary(counts: dict[str, int]) -> str:
    return ", ".join(
        f"{label}: {count}"
        for label, count in sorted(counts.items(), key=lambda item: item[0].casefold())
    )


def _render_evidence_gap_review_queue(view_model: dict[str, object]) -> None:
    queue = evidence_gap_queue.build_plant_promoter_evidence_gap_review_queue(view_model)
    summary = queue.get("summary_counts") if isinstance(queue.get("summary_counts"), dict) else {}
    category_counts = _text_int_map(queue.get("category_counts"))
    queue_rows = _build_evidence_gap_queue_rows(_row_list(queue.get("queue_item_rows")))
    boundary_notes = _option_values(queue.get("boundary_notes"))

    with st.expander("Plant Promoter Evidence Gap Review Queue", expanded=False):
        st.caption(
            "Read-only evidence gap review queue for documentation review and human curation only."
        )
        if boundary_notes:
            for note in boundary_notes:
                st.caption(note)
        st.caption(f"Total queue items: {int(summary.get('queue_item_count') or 0)}")
        if category_counts:
            st.caption("Counts by category: " + _format_count_summary(category_counts))
        if queue_rows:
            st.dataframe(
                pd.DataFrame(queue_rows, columns=EVIDENCE_GAP_QUEUE_COLUMNS),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No evidence gap queue items are visible for the current documentation scope.")


def _render_selected_profile_detail(profile_rows: list[dict[str, object]]) -> None:
    profile_ids = [_text(row.get("part_id")) for row in profile_rows if _text(row.get("part_id"))]
    if not profile_ids:
        return
    selected_part_id = st.selectbox(
        "Promoter profile detail",
        options=profile_ids,
        format_func=lambda part_id: next(
            (
                _text(row.get("display_name"), part_id)
                for row in profile_rows
                if _text(row.get("part_id")) == _text(part_id)
            ),
            str(part_id),
        ),
        key="plant_promoter_catalog_profile_detail",
    )
    detail = workspace_presenter.build_profile_detail_view_model(selected_part_id)
    if detail.get("status") != "available":
        st.info(str(detail.get("message") or "No selected promoter profile detail is available."))
        return

    summary = detail.get("profile_summary") if isinstance(detail.get("profile_summary"), dict) else {}
    st.markdown("**Selected profile documentation detail**")
    st.caption(str(detail.get("boundary_note") or workspace_presenter.CATALOG_REFERENCE_BOUNDARY_NOTE))
    st.caption(str(detail.get("limitation_note") or workspace_presenter.CATALOG_REFERENCE_LIMITATION_NOTE))
    st.caption(f"Catalog source: {summary.get('catalog_record_source') or 'local Parts Registry'}")
    limitation_notes = _text(summary.get("limitation_notes"))
    if limitation_notes:
        st.caption(f"Limitation notes: {limitation_notes}")
    st.dataframe(
        pd.DataFrame(_build_profile_table_rows([summary]), columns=PROFILE_COLUMNS),
        hide_index=True,
        use_container_width=True,
    )

    evidence_rows = _row_list(detail.get("evidence_rows"))
    st.markdown("**Tissue-context evidence rows**")
    if evidence_rows:
        st.dataframe(
            pd.DataFrame(_build_detail_evidence_rows(evidence_rows), columns=DETAIL_EVIDENCE_COLUMNS),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No tissue-context evidence rows are recorded for the selected promoter profile.")

    motif_rows = _row_list(detail.get("motif_annotation_rows"))
    st.markdown("**Child motif rows**")
    if motif_rows:
        st.dataframe(
            pd.DataFrame(_build_detail_motif_rows(motif_rows), columns=DETAIL_MOTIF_COLUMNS),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No motif annotation rows are recorded for the selected promoter profile.")

    source_rows = _row_list(detail.get("source_review_metadata_rows"))
    st.markdown("**Source and review metadata**")
    if source_rows:
        st.dataframe(
            pd.DataFrame(_build_source_review_rows(source_rows), columns=SOURCE_REVIEW_COLUMNS),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption(
            "No source/review metadata rows are recorded for the selected promoter profile; treat this as a metadata gap for documentation review."
        )


def _render_project_reference_panel(profile_rows: list[dict[str, object]]) -> None:
    profile_ids = [_text(row.get("part_id")) for row in profile_rows if _text(row.get("part_id"))]
    st.markdown("**Project documentation reference**")
    st.caption(
        "Add a plant promoter asset profile from the Component Library as a documentation-level project reference. "
        "This records catalog metadata context only and does not change catalog records."
    )
    st.caption(
        "Reference bridge fields for workflow use are the record identifier, linked catalog context, catalog source/status, "
        "project documentation context, and local project documentation note."
    )
    st.caption(str(workspace_presenter.CATALOG_REFERENCE_BOUNDARY_NOTE))
    if not profile_ids:
        st.info("No promoter profile is available for project reference linking.")
        return

    project_id = st.text_input(
        "Pathway project ID",
        value="",
        key="plant_promoter_catalog_project_reference_project_id",
        placeholder="Enter an existing local project ID",
    )
    selected_part_id = st.selectbox(
        "Plant promoter profile for project reference",
        options=profile_ids,
        format_func=lambda part_id: next(
            (
                _text(row.get("display_name"), part_id)
                for row in profile_rows
                if _text(row.get("part_id")) == _text(part_id)
            ),
            str(part_id),
        ),
        key="plant_promoter_catalog_project_reference_part_id",
    )
    note = st.text_area(
        "Project reference note",
        value=workspace_presenter.DEFAULT_REFERENCE_NOTE,
        key="plant_promoter_catalog_project_reference_note",
        height=90,
        placeholder="Optional local review note",
    )
    project_documentation_context = st.text_input(
        "Project documentation context",
        value="Pathway Workspace linked catalog assets",
        key="plant_promoter_catalog_project_reference_context",
        help="Documentation-only context for where this catalog profile should be linked inside the project.",
    )
    if st.button(
        "Add reference to project documentation",
        key="plant_promoter_catalog_project_reference_add",
        use_container_width=True,
    ):
        if not _text(project_id):
            st.info("Enter a pathway project ID before saving the documentation reference.")
            return
        try:
            link = workspace_presenter.build_promoter_catalog_project_link(
                project_id=project_id,
                part_id=selected_part_id,
                documentation_note=note or workspace_presenter.DEFAULT_REFERENCE_NOTE,
                linked_at="project_reference_panel",
            )
        except ValueError as exc:
            st.error(str(exc))
            return
        source_snapshot = (
            link.get("source_context_snapshot")
            if isinstance(link.get("source_context_snapshot"), dict)
            else {}
        )
        source_snapshot["project_documentation_context"] = (
            project_documentation_context or "Pathway Workspace linked catalog assets"
        )
        link["source_context_snapshot"] = source_snapshot
        basket_entry = basket_service.build_catalog_reference_basket_entry(
            project_id=project_id,
            link_payload=link,
            project_documentation_context=project_documentation_context or "Pathway Workspace linked catalog assets",
            documentation_note=note or workspace_presenter.DEFAULT_REFERENCE_NOTE,
        )
        try:
            existing_link = project_catalog_link_repo.find_project_catalog_asset_link(
                project_id,
                asset_id=basket_entry.get("asset_id"),
                linkage_role=basket_entry.get("linkage_role"),
            )
        except Exception:
            existing_link = {}
        if existing_link:
            st.info(
                "This linked catalog reference is already linked to project documentation for the selected project and role."
            )
            return
        added, _existing = basket_service.add_catalog_reference_basket_entry(st.session_state, basket_entry)
        if added:
            st.success(basket_service.STAGED_REFERENCE_ADDED_COPY)
            st.caption(basket_service.BASKET_BOUNDARY_COPY)
        else:
            st.info(basket_service.STAGED_REFERENCE_DUPLICATE_COPY)


def _selectbox(label: str, options: list[str], key: str) -> str:
    return st.selectbox(label, options=options, key=key)


def render() -> None:
    inject_tool_typography_css()
    render_tool_header(PAGE_TITLE, PAGE_SUBTITLE)
    render_boundary_note(BOUNDARY_COPY)
    render_tool_intro("Documentation-only browse", INTRO_COPY)
    render_help_text(FILTER_HELP_COPY)

    unfiltered = _sanitize_view_model(presenter.build_plant_promoter_catalog_view_model())
    clade_options = ["all"] + _option_values(unfiltered.get("available_plant_clades"))
    tissue_options = ["all"] + _option_values(unfiltered.get("available_tissue_contexts"))

    filter_cols = st.columns(5)
    with filter_cols[0]:
        selected_clade = _selectbox("Plant clade", clade_options, "plant_promoter_catalog_clade")
    with filter_cols[1]:
        selected_species = _selectbox(
            "Species",
            ["all"] + _option_values(unfiltered.get("available_species")),
            "plant_promoter_catalog_species",
        )
    with filter_cols[2]:
        selected_tissue = _selectbox("Tissue context", tissue_options, "plant_promoter_catalog_tissue")
    with filter_cols[3]:
        selected_evidence_type = _selectbox(
            "Evidence type",
            ["all"] + _option_values(unfiltered.get("available_evidence_types")),
            "plant_promoter_catalog_evidence_type",
        )
    with filter_cols[4]:
        selected_curation_status = _selectbox(
            "Curation status",
            ["all"] + _option_values(unfiltered.get("available_curation_statuses")),
            "plant_promoter_catalog_curation_status",
        )

    view_model = _sanitize_view_model(
        presenter.build_plant_promoter_catalog_view_model(
            plant_clade=selected_clade,
            species=selected_species,
            tissue_context=selected_tissue,
            evidence_type=selected_evidence_type,
            curation_status=selected_curation_status,
        )
    )
    summary = view_model["summary_counts"]
    total_profile_records = max(view_model["persistent_profile_count"], view_model["seed_profile_count"])
    total_profile_scope = (
        "Bundled promoter-specific/reference records"
        if view_model["seed_profile_count"] > 0 and view_model["persistent_profile_count"] == 0
        else "Persistent promoter-specific/reference records"
    )
    record_context_label = (
        "seed/demo data context"
        if view_model["seed_profile_count"] > 0 and view_model["persistent_profile_count"] == 0
        else "persistent database context"
    )

    render_compact_summary_cards(
        [
            ("Profile rows", str(total_profile_records), total_profile_scope),
            ("Filtered table rows", str(summary["profile_count"]), "Current filter matches"),
            ("Child tissue evidence rows", str(summary["tissue_evidence_count"]), "Current filtered rows"),
            ("Child motif rows", str(summary["motif_annotation_count"]), "Row granularity: motif rows"),
            ("Review-needed rows", str(summary["rows_needing_review_count"]), "Manual confirmation required"),
            ("Source family rows", str(summary["source_database_count"]), "Distinct source database labels"),
            ("Linked catalog references", str(summary["linked_catalog_reference_count"]), "Distinct source database labels"),
        ]
    )
    st.caption(_text(view_model.get("boundary_note"), presenter.BOUNDARY_NOTE))
    st.caption(
        "Source family: Plant Promoter Catalog. "
        "Record scope: profile rows plus child evidence and review rows. "
        "Catalog record context: "
        f"{record_context_label}; {_text(view_model.get('catalog_status_label'), 'catalog records')} shown as "
        f"{_text(view_model.get('documentation_status_label'), 'documentation-only reference records')}."
    )
    st.caption(
        f"Filtered table rows are counted separately from the profile row scope ({total_profile_records})."
    )
    if view_model["persistent_profile_count"] == 0 and view_model["seed_profile_count"] > 0:
        st.info(
            "Persistent promoter profile tables are currently empty, so bundled seed records are supplying the local documentation view."
        )
    if _text(view_model.get("catalog_source")) == "local curated sample records":
        seed_metadata = view_model.get("seed_metadata") if isinstance(view_model.get("seed_metadata"), dict) else {}
        st.info("Local curated sample records are shown as documentation-level catalog context.")
        seed_name = _text(seed_metadata.get("seed_name"))
        seed_version = _text(seed_metadata.get("seed_version"))
        if seed_name or seed_version:
            st.caption(f"Seed metadata: {seed_name} {seed_version}".strip())
        st.caption(
            "This view keeps source/review metadata and limitation notes visible; it does not provide selection advice, certification, or behavior forecasts."
        )
        for warning in _option_values(view_model.get("seed_warnings")):
            st.caption(warning)
    tissue_summary = _text_int_map(view_model.get("tissue_context_evidence_summary"))
    if tissue_summary:
        st.caption("Tissue evidence metadata summary: " + _format_count_summary(tissue_summary))
    source_evidence_labels = _option_values(view_model.get("source_evidence_labels"))
    if source_evidence_labels:
        preview_labels = source_evidence_labels[:6]
        suffix = "" if len(source_evidence_labels) <= 6 else f"; +{len(source_evidence_labels) - 6} more"
        st.caption("Source evidence context labels: " + "; ".join(preview_labels) + suffix)
    source_labels = _option_values(view_model.get("represented_source_database_labels"))
    if source_labels:
        st.caption("Source database groups represented: " + ", ".join(source_labels))

    profile_rows = _row_list(view_model.get("profile_rows"))
    evidence_rows = _row_list(view_model.get("evidence_rows"))
    _render_evidence_gap_review_queue(view_model)
    has_active_filters = any(
        value != "all"
        for value in (
            selected_clade,
            selected_species,
            selected_tissue,
            selected_evidence_type,
            selected_curation_status,
        )
    )

    if not profile_rows:
        st.info(
            "No promoter profiles are present for the current local documentation scope. "
            "Persistent profile tables are empty and no bundled seed records are available for this browse surface."
        )
        return

    if not evidence_rows:
        if has_active_filters:
            st.info(
                "No tissue evidence rows match the current filters. Adjust the filter controls to continue browsing the catalog."
            )
        else:
            st.info(
                "No tissue evidence rows are recorded for the current promoter profiles. "
                "Unknown tissue context and missing source database labels remain metadata gaps until evidence rows are added."
            )
        return

    st.dataframe(
        pd.DataFrame(_build_table_rows(evidence_rows), columns=TABLE_COLUMNS),
        hide_index=True,
        use_container_width=True,
    )
    st.markdown("**Filtered table rows**")
    st.caption(f"Showing {len(evidence_rows)} tissue evidence rows across {len(profile_rows)} of {total_profile_records} profile rows.")
    st.caption(
        "Missing tissue context and missing source database values are shown with explicit fallback labels so evidence metadata gaps remain visible."
    )

    with st.expander("Promoter asset rows and review readback", expanded=False):
        st.caption(
            "Source-recorded species, clade, tissue evidence metadata, and review gaps are grouped here as review context; "
            "this is not host compatibility proof, a promoter recommendation, or a wet-lab readiness judgment."
        )
        st.markdown("**Host/tissue readback rows**")
        st.caption(
            "Context readback summarizes source-recorded species, clade, tissue evidence metadata, and review gaps; "
            "it is not host compatibility proof, not a promoter recommendation, and not a wet-lab readiness judgment."
        )
        readback_rows = _build_host_tissue_readback_rows(
            profile_rows,
            evidence_rows,
            _row_list(view_model.get("rows_needing_review")),
        )
        if readback_rows:
            st.dataframe(
                pd.DataFrame(readback_rows, columns=HOST_TISSUE_READBACK_COLUMNS),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No host/tissue context readback rows are visible for the current filters.")

        st.markdown("**Catalog context readback rows**")
        st.caption(
            _text(
                view_model.get("documentation_only_context_note"),
                presenter.READBACK_BOUNDARY_NOTE,
            )
        )
        st.caption(
            "Each row keeps catalog context, tissue evidence context, source context, review metadata, and metadata gaps visible for manual review."
        )
        context_readback_rows = _build_context_readback_rows(_row_list(view_model.get("context_readback_rows")))
        if context_readback_rows:
            st.dataframe(
                pd.DataFrame(context_readback_rows, columns=CONTEXT_READBACK_COLUMNS),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No catalog context readback rows are visible for the current filters.")

        st.markdown("**Review-needed rows**")
        st.caption(
            "Rows here need source or metadata review before citation in project documentation; "
            "this is not a biological recommendation, host compatibility proof, or wet-lab use guidance."
        )
        review_needed_rows = _build_review_needed_rows(_row_list(view_model.get("rows_needing_review")))
        if review_needed_rows:
            st.dataframe(
                pd.DataFrame(review_needed_rows, columns=REVIEW_NEEDED_COLUMNS),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No review-needed tissue evidence rows are visible for the current filters.")

        motif_rows = _build_motif_rows(_row_list(view_model.get("motif_preview_rows")))
        if motif_rows:
            st.markdown("**Motif annotation preview rows**")
            st.dataframe(
                pd.DataFrame(motif_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("No motif annotation rows are recorded for the currently visible promoter profiles.")

    with st.expander("Promoter project reference rows", expanded=False):
        _render_project_reference_panel(profile_rows)
    with st.expander("Selected promoter profile row detail", expanded=False):
        _render_selected_profile_detail(profile_rows)
