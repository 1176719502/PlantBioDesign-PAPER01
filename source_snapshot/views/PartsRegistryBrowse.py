from __future__ import annotations

import pandas as pd
import streamlit as st

from services import parts_registry_repository as repo
from services import parts_registry_write_service as write_service
from services.parts_registry_browse_presenter import (
    build_parts_browse_records,
    build_registry_inventory_summary,
    table_rows,
)
from views.tool_typography import render_compact_summary_cards


EMPTY_STATE_COPY = (
    "No local catalog records are present. The local parts catalog is a "
    "documentation-only browse surface for provenance context, metadata "
    "completeness, source notes, and human review status."
)

BOUNDARY_COPY = (
    "Read-only local parts catalog. Records support documentation-only "
    "provenance context and curation status review; they do not provide "
    "selection guidance, prediction, external "
    "database integration, project linkage creation, pathway "
    "linkage creation, saved-design linkage creation, import/export payload changes, package "
    "schema changes, or Expression Wizard and primer propagation changes."
)

LINKAGE_SECTION_COPY = (
    "Read-only documentation traceability for linked documentation records. "
    "Use this provenance context for metadata completeness and human review context."
)

ADMIN_BOUNDARY_COPY = (
    "Manual entry appends documentation-only local catalog records for provenance, "
    "annotation, review status, and traceability context. It does not delete records, "
    "sync external databases, change package manifests, or provide selection guidance."
)

PART_TYPE_ALL_LABEL = "All part types"
CURATION_STATUS_ALL_LABEL = "All curation statuses"


def _part_options(records: list[dict]) -> list[str]:
    return [str(record.get("local_id") or "") for record in records if record.get("local_id")]


def _version_options(local_id: str) -> list[str]:
    return [""] + [str(row["id"]) for row in repo.list_versions_for_part(local_id)]


def _version_id(value: str | None) -> int | None:
    text = str(value or "").strip()
    return int(text) if text else None


def _show_write_result(result: dict) -> None:
    if result.get("ok"):
        st.success("Local catalog documentation record saved.")
        return
    st.error(str(result.get("error") or "Local catalog record was not saved."))


def _selected_part_for_form(records: list[dict], key: str) -> str:
    options = _part_options(records)
    if not options:
        return ""
    return st.selectbox("Local part record", options, key=key)


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value or "").strip()}, key=str.casefold)


def _browse_search_blob(record: dict) -> str:
    fields = (
        record.get("local_id"),
        record.get("display_name"),
        record.get("part_type"),
        record.get("version_label"),
        record.get("sequence_metadata"),
        record.get("curation_status"),
        record.get("human_review_status"),
        record.get("source_note_count"),
        record.get("linkage_record_count"),
    )
    return " ".join(str(value or "") for value in fields).casefold()


def _filter_records(records: list[dict], *, search_query: str, part_type: str, curation_status: str) -> list[dict]:
    search = str(search_query or "").strip().casefold()
    part_type_value = str(part_type or "").strip()
    curation_value = str(curation_status or "").strip()
    filtered: list[dict] = []
    for record in records:
        if part_type_value and part_type_value != PART_TYPE_ALL_LABEL and str(record.get("part_type") or "") != part_type_value:
            continue
        if curation_value and curation_value != CURATION_STATUS_ALL_LABEL and str(record.get("curation_status") or "") != curation_value:
            continue
        if search and search not in _browse_search_blob(record):
            continue
        filtered.append(record)
    return filtered


def _part_type_options(records: list[dict]) -> list[str]:
    return [PART_TYPE_ALL_LABEL, *_unique_sorted([str(record.get("part_type") or "") for record in records])]


def _curation_status_options(records: list[dict]) -> list[str]:
    return [CURATION_STATUS_ALL_LABEL, *_unique_sorted([str(record.get("curation_status") or "") for record in records])]


def _render_create_local_part_form() -> None:
    with st.form("parts_catalog_create_local_part_form"):
        local_id = st.text_input("Local ID", key="parts_catalog_create_local_id")
        part_type = st.selectbox("Part type", repo.PART_TYPE_VOCABULARY, key="parts_catalog_create_part_type")
        display_name = st.text_input("Display name", key="parts_catalog_create_display_name")
        description = st.text_area("Description", key="parts_catalog_create_description")
        if st.form_submit_button("Create local part", key="parts_catalog_create_submit"):
            _show_write_result(
                write_service.create_local_part(
                    local_id=local_id,
                    part_type=part_type,
                    display_name=display_name,
                    description=description,
                )
            )


def _render_add_version_form(records: list[dict]) -> None:
    with st.form("parts_catalog_add_version_form"):
        local_id = _selected_part_for_form(records, "parts_catalog_version_part")
        version_label = st.text_input("Version label", key="parts_catalog_version_label")
        sequence = st.text_area("Sequence metadata", key="parts_catalog_version_sequence")
        sequence_hash = st.text_input("Sequence hash", key="parts_catalog_version_hash")
        sequence_hash_algorithm = st.text_input("Sequence hash algorithm", key="parts_catalog_version_hash_algorithm")
        version_note = st.text_area("Version note", key="parts_catalog_version_note")
        if st.form_submit_button("Add part version", key="parts_catalog_version_submit"):
            _show_write_result(
                write_service.add_part_version(
                    part_local_id=local_id,
                    version_label=version_label,
                    sequence=sequence or None,
                    sequence_hash=sequence_hash or None,
                    sequence_hash_algorithm=sequence_hash_algorithm or None,
                    version_note=version_note,
                )
            )


def _render_add_source_form(records: list[dict]) -> None:
    with st.form("parts_catalog_add_source_form"):
        local_id = _selected_part_for_form(records, "parts_catalog_source_part")
        version_id = st.selectbox("Version context", _version_options(local_id), key="parts_catalog_source_version")
        source_name = st.text_input("Source name", key="parts_catalog_source_name")
        source_reference = st.text_input("Source reference", key="parts_catalog_source_reference")
        source_context = st.text_area("Source context", key="parts_catalog_source_context")
        provenance_note = st.text_area("Provenance note", key="parts_catalog_source_note")
        if st.form_submit_button("Add source/provenance note", key="parts_catalog_source_submit"):
            _show_write_result(
                write_service.add_part_source(
                    part_local_id=local_id,
                    part_version_id=_version_id(version_id),
                    source_name=source_name,
                    source_reference=source_reference,
                    organism_or_source_context=source_context,
                    provenance_note=provenance_note,
                )
            )


def _render_add_annotation_form(records: list[dict]) -> None:
    with st.form("parts_catalog_add_annotation_form"):
        local_id = _selected_part_for_form(records, "parts_catalog_annotation_part")
        version_id = st.selectbox("Version context", _version_options(local_id), key="parts_catalog_annotation_version")
        annotation_type = st.text_input("Annotation type", value="documentation note", key="parts_catalog_annotation_type")
        annotation_text = st.text_area("Annotation text", key="parts_catalog_annotation_text")
        if st.form_submit_button("Add annotation", key="parts_catalog_annotation_submit"):
            _show_write_result(
                write_service.add_part_annotation(
                    part_local_id=local_id,
                    part_version_id=_version_id(version_id),
                    annotation_type=annotation_type,
                    annotation_text=annotation_text,
                )
            )


def _render_add_review_status_form(records: list[dict]) -> None:
    with st.form("parts_catalog_add_review_status_form"):
        local_id = _selected_part_for_form(records, "parts_catalog_review_part")
        version_id = st.selectbox("Version context", _version_options(local_id), key="parts_catalog_review_version")
        curation_status = st.selectbox("Curation status", repo.CURATION_STATUS_TERMS, key="parts_catalog_curation_status")
        human_review_status = st.selectbox("Human review status", repo.HUMAN_REVIEW_STATUS_TERMS, key="parts_catalog_human_review_status")
        review_note = st.text_area("Review note", key="parts_catalog_review_note")
        reviewer = st.text_input("Reviewer name or initials", key="parts_catalog_reviewer")
        reviewed_at = st.text_input("Reviewed at", key="parts_catalog_reviewed_at")
        if st.form_submit_button("Add review status", key="parts_catalog_review_submit"):
            _show_write_result(
                write_service.add_part_review_status(
                    part_local_id=local_id,
                    part_version_id=_version_id(version_id),
                    curation_status=curation_status,
                    human_review_status=human_review_status,
                    review_note=review_note,
                    reviewer_name_or_initials=reviewer,
                    reviewed_at=reviewed_at or None,
                )
            )


def _render_add_link_form(records: list[dict]) -> None:
    with st.form("parts_catalog_add_link_form"):
        local_id = _selected_part_for_form(records, "parts_catalog_link_part")
        version_id = st.selectbox("Version context", _version_options(local_id), key="parts_catalog_link_version")
        target_type = st.selectbox("Target type", repo.PART_LINK_TARGET_TYPES, key="parts_catalog_link_target_type")
        target_id = st.text_input("Target ID", key="parts_catalog_link_target_id")
        target_label = st.text_input("Target label snapshot", key="parts_catalog_link_target_label")
        link_note = st.text_area("Link note", key="parts_catalog_link_note")
        review_status = st.selectbox("Traceability review status", repo.PART_LINK_REVIEW_STATUS_TERMS, key="parts_catalog_link_review_status")
        if st.form_submit_button("Add documentation traceability link", key="parts_catalog_link_submit"):
            _show_write_result(
                write_service.add_part_link(
                    part_local_id=local_id,
                    part_version_id=_version_id(version_id),
                    target_type=target_type,
                    target_id=target_id,
                    target_label=target_label,
                    link_note=link_note,
                    review_status=review_status,
                )
            )


def render_admin_section(records: list[dict] | None = None) -> None:
    records = records if records is not None else build_parts_browse_records()
    st.subheader("Local parts catalog manual entry")
    st.caption(ADMIN_BOUNDARY_COPY)
    with st.expander("Add local catalog documentation records", expanded=False):
        _render_create_local_part_form()
        if not records:
            st.info("Create a local part record before adding versions, source notes, annotations, review status, or traceability links.")
            return
        (
            version_tab,
            source_tab,
            annotation_tab,
            review_tab,
            link_tab,
        ) = st.tabs(
            [
                "Version",
                "Source/provenance",
                "Annotation",
                "Review status",
                "Traceability link",
            ]
        )
        with version_tab:
            _render_add_version_form(records)
        with source_tab:
            _render_add_source_form(records)
        with annotation_tab:
            _render_add_annotation_form(records)
        with review_tab:
            _render_add_review_status_form(records)
        with link_tab:
            _render_add_link_form(records)


def _show_records(label: str, records: list[dict]) -> None:
    st.markdown(f"**{label}**")
    if not records:
        st.caption("No documentation records in this section.")
        return
    st.dataframe(pd.DataFrame(records), hide_index=True)


def render_panel(*, show_admin: bool = True) -> None:
    st.subheader("Local parts catalog")
    st.caption(BOUNDARY_COPY)
    st.caption("Source family: Parts Registry. Record scope: saved local registry rows. Row granularity: part records, version rows, source rows, review rows, and traceability link rows.")

    records = build_parts_browse_records()
    summary = build_registry_inventory_summary(records)
    render_compact_summary_cards(
        [
            ("Saved registry rows", str(summary["part_record_count"]), "Source family: Parts Registry; record scope: saved local registry rows"),
            ("Part type groups", str(summary["part_type_count"]), summary["record_source_label"]),
            ("Version rows", str(summary["version_record_count"]), "Row granularity: version labels and sequence metadata notes"),
            ("Source/provenance rows", str(summary["source_note_count"]), "Row granularity: provenance context rows"),
            ("Traceability link rows", str(summary["linked_traceability_count"]), "Row granularity: linked documentation records"),
        ]
    )
    st.caption(
        "Saved registry rows stay separate from bundled catalog rows on the Data page. "
        "If this section is empty, bundled seed catalogs may still be available elsewhere on the Data page."
    )
    if summary["counts_by_part_type"]:
        st.caption(
            "Persistent part types: "
            + ", ".join(f"{label}: {count}" for label, count in summary["counts_by_part_type"].items())
        )

    if show_admin:
        render_admin_section(records)
    if not records:
        st.info(
            f"{EMPTY_STATE_COPY} Persistent records are currently 0 in the read-only local registry schema, "
            "but bundled seed records may still be available in the Local Design Asset Catalog and Plant Promoter Catalog browse surfaces."
        )
        return

    filter_cols = st.columns([1.8, 1, 1], gap="small")
    with filter_cols[0]:
        search_query = st.text_input(
            "Search local catalog",
            key="parts_registry_search_query",
            placeholder="Search local ID, display name, type, or review status",
        )
    with filter_cols[1]:
        selected_part_type = st.selectbox(
            "Part type",
            options=_part_type_options(records),
            key="parts_registry_part_type_filter",
        )
    with filter_cols[2]:
        selected_curation_status = st.selectbox(
            "Curation status",
            options=_curation_status_options(records),
            key="parts_registry_curation_status_filter",
        )

    filtered_records = _filter_records(
        records,
        search_query=search_query,
        part_type=selected_part_type,
        curation_status=selected_curation_status,
    )
    st.caption(f"Showing {len(filtered_records)} of {len(records)} saved registry rows after local browse filters.")
    if not filtered_records:
        st.info("No saved registry rows match the current local catalog search and filter settings.")
        return

    st.markdown("**Saved registry table rows**")
    st.caption(
        f"Showing {len(filtered_records)} of {summary['part_record_count']} saved registry rows. "
        "Bundled local design assets and promoter-specific/reference rows are counted separately on their own browse surfaces."
    )
    st.dataframe(pd.DataFrame(table_rows(filtered_records)), hide_index=True)

    for record in filtered_records:
        title = f"{record['display_name']} - {record['part_type']}"
        with st.expander(title, expanded=False):
            st.markdown(f"**Local id:** {record['local_id']}")
            st.markdown(f"**Current/version label:** {record['version_label']}")
            st.markdown(f"**Sequence metadata:** {record['sequence_metadata']}")
            st.markdown(f"**Source notes:** {record['source_note_count']}")
            st.markdown(f"**Traceability links:** {record['linkage_record_count']}")
            st.markdown(f"**Curation status:** {record['curation_status']}")
            st.markdown(f"**Human review:** {record['human_review_status']}")
            _show_records("Versions", record["versions"])
            _show_records("Source/provenance records", record["sources"])
            _show_records("Annotations", record["annotations"])
            _show_records("Review status records", record["review_statuses"])
            st.markdown("**Documentation traceability**")
            st.caption(LINKAGE_SECTION_COPY)
            _show_records("Linked documentation records", record["linkage_records"])
