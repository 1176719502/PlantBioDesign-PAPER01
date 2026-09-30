from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services import catalog_reference_basket_service as basket_service
from services import project_catalog_asset_link_repository as persistent_links
from services.catalog_asset_snapshot_builder import (
    build_catalog_asset_snapshot,
    catalog_asset_snapshot_has_content,
)
from services.local_design_asset_catalog_service import (
    asset_preview,
    asset_selector_label,
    load_seed_records,
    search_assets,
)
from services.project_asset_linkage_service import (
    ALLOWED_LINKAGE_ROLES,
    build_project_asset_link,
    list_project_asset_links,
    merge_project_asset_links,
    report_links_needing_review,
    summarize_project_asset_links,
)
from services.plant_promoter_catalog_workspace_presenter import (
    CATALOG_REFERENCE_BOUNDARY_NOTE,
    CATALOG_REFERENCE_LIMITATION_NOTE,
    DEFAULT_REFERENCE_NOTE as DEFAULT_PROMOTER_REFERENCE_NOTE,
    EMPTY_CATALOG_REFERENCE_MESSAGE,
    PLANT_PROMOTER_PROFILE_ASSET_TYPE,
    build_catalog_reference_options,
    build_profile_detail_view_model,
    build_promoter_catalog_project_link,
    summarize_linked_plant_promoter_references,
)
from services.project_catalog_reference_output_formatter import build_linked_catalog_reference_output
from views import tool_typography

LINKED_CATALOG_ASSETS_BOUNDARY_COPY = (
    "Linked assets are documentation references only. "
    "Linking an asset does not indicate biological fit, source verification, or downstream use state. "
    "Human review is required before downstream use; links do not endorse or select an asset."
)
LINKED_CATALOG_ASSETS_SUMMARY_NOTE = "Linked catalog references can point to persistent records, bundled seed records, example catalog records, or documentation-only reference records."
LINKED_CATALOG_ASSETS_EMPTY_STATE_COPY = (
    "No linked catalog references are recorded for this project yet. "
    "Add catalog records when project documentation needs reference-only source, review, or traceability context."
)
LINKED_CATALOG_REFERENCE_EXISTS_COPY = (
    "This linked catalog reference is already linked to project documentation for the active project and selected role."
)
LINKED_CATALOG_REFERENCE_EXISTS_AND_STAGED_REMOVED_COPY = (
    "This linked catalog reference is already linked to project documentation for the active project and selected role. "
    "The staged documentation reference was removed from the basket."
)
LINKED_CATALOG_ASSETS_ADD_PANEL_COPY = "Add catalog asset reference"
LINKED_CATALOG_ASSETS_STORAGE_KEY_TEMPLATE = "project_asset_links_{project_id}"
DEFAULT_DOCUMENTATION_NOTE = "Documentation-only reference for project traceability."
DEFAULT_PROJECT_DOCUMENTATION_CONTEXT = "Pathway Workspace linked catalog assets"
PROMOTER_CONTEXT_READBACK_COLUMNS = [
    "Component Library promoter asset",
    "Species or clade context",
    "Tissue evidence context",
    "Source/review metadata",
    "Metadata gap",
    "Manual review note",
]
PROMOTER_READBACK_EMPTY_WITH_GENERIC_LINKS_COPY = (
    "No Component Library promoter asset context readback rows are available for the current linked catalog assets. "
    "Generic linked catalog references remain visible below as documentation-only references."
)
PROMOTER_READBACK_EMPTY_NO_PROMOTER_COPY = (
    "No Component Library promoter asset references are linked yet. Generic linked catalog references, if present, remain listed below as documentation-only references."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _asset_links_source(project: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []

    for key in ("project_asset_links", "asset_links", "linked_catalog_assets"):
        value = project.get(key)
        if isinstance(value, list):
            return [dict(link) for link in value if isinstance(link, dict)]

    session_value = st.session_state.get(f"project_asset_links_{project.get('id')}")
    if isinstance(session_value, list):
        return [dict(link) for link in session_value if isinstance(link, dict)]

    return []


def _project_links_storage_key(project_id: Any) -> str:
    return LINKED_CATALOG_ASSETS_STORAGE_KEY_TEMPLATE.format(project_id=project_id)


def project_links_storage_key(project_id: Any) -> str:
    """Return the shared session key for project catalog reference links."""
    return _project_links_storage_key(project_id)


def _persisted_project_links(project_id: Any) -> list[dict[str, Any]]:
    try:
        return persistent_links.list_project_catalog_asset_links(project_id)
    except Exception:
        return []


def _combined_project_links(project: dict[str, Any]) -> list[dict[str, Any]]:
    payload_links: list[dict[str, Any]] = []
    for key in ("project_asset_links", "asset_links", "linked_catalog_assets"):
        value = project.get(key)
        if isinstance(value, list):
            payload_links.extend(dict(link) for link in value if isinstance(link, dict))
    persisted_links = _persisted_project_links(project.get("id"))
    session_links = st.session_state.get(_project_links_storage_key(project.get("id")))
    if isinstance(session_links, list):
        return merge_project_asset_links(persisted_links, payload_links, session_links)
    return merge_project_asset_links(persisted_links, payload_links)


def _find_persisted_project_link(
    project_id: Any,
    *,
    asset_id: Any,
    linkage_role: Any,
) -> dict[str, Any]:
    try:
        return persistent_links.find_project_catalog_asset_link(
            project_id,
            asset_id=asset_id,
            linkage_role=linkage_role,
        )
    except Exception:
        return {}


def _asset_link_rows(project: dict[str, Any]) -> list[dict[str, Any]]:
    links = list_project_asset_links(_combined_project_links(project), project_id=project.get("id"))
    return _asset_link_rows_from_links(links)


def _asset_link_rows_from_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for link in links:
        rows.append(build_linked_catalog_reference_output(link))
    return rows


def _snapshot_text(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if item not in (None, "", [], {}):
                parts.append(f"{key}: {item}")
        return "; ".join(parts) if parts else "Not recorded"
    return str(value or "Not recorded")


def _selected_asset_record(records: list[dict[str, Any]], asset_id: Any) -> dict[str, Any]:
    target_id = str(asset_id or "").strip()
    return next((dict(record) for record in records if str(record.get("asset_id") or "").strip() == target_id), {})


def _selected_promoter_option(options: list[dict[str, Any]], part_id: Any) -> dict[str, Any]:
    target_id = str(part_id or "").strip()
    return next((dict(row) for row in options if str(row.get("part_id") or "").strip() == target_id), {})


def _render_selected_asset_preview(record: dict[str, Any]) -> None:
    preview = asset_preview(record)
    with st.container(border=True):
        st.caption("Selected asset preview")
        st.markdown(f"**display_name:** {preview['display_name']}")
        st.markdown(f"**asset_type:** {preview['asset_type']}")
        st.markdown(f"**source/provenance status:** {preview['source_or_provenance_status']}")
        st.markdown(f"**review status:** {preview['review_status']}")
        st.markdown(f"**human review note:** {preview['human_review_note']}")


def _render_selected_promoter_preview(part_id: Any) -> None:
    detail = build_profile_detail_view_model(part_id)
    summary = detail.get("profile_summary") if isinstance(detail.get("profile_summary"), dict) else {}
    if not summary:
        return
    with st.container(border=True):
        st.caption("Selected Component Library promoter asset preview")
        st.markdown(f"**promoter_label:** {summary.get('promoter_label') or 'Not recorded'}")
        st.markdown(f"**plant_clade:** {summary.get('plant_clade') or 'Not recorded'}")
        st.markdown(f"**species:** {summary.get('species_label') or 'Not recorded'}")
        st.markdown(f"**tissue evidence rows:** {summary.get('evidence_row_count', 0)}")
        st.markdown(f"**motif annotation rows:** {summary.get('motif_annotation_count', 0)}")
        st.markdown(f"**missing metadata count:** {detail.get('missing_metadata_count', 0)}")


def _promoter_context_readback_rows(project_links: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    promoter_links = summarize_linked_plant_promoter_references(project_links).get("references") or []
    for link in list_project_asset_links(project_links):
        if _text(link.get("asset_type")) != PLANT_PROMOTER_PROFILE_ASSET_TYPE:
            continue
        source_snapshot = (
            dict(link.get("source_context_snapshot"))
            if isinstance(link.get("source_context_snapshot"), dict)
            else {}
        )
        review_snapshot = (
            dict(link.get("review_status_snapshot"))
            if isinstance(link.get("review_status_snapshot"), dict)
            else {}
        )
        matched_reference = next(
            (
                reference
                for reference in promoter_links
                if _text(reference.get("asset_id")) == _text(link.get("asset_id"))
            ),
            {},
        )
        promoter_label = _text(
            matched_reference.get("asset_display_name")
            or link.get("asset_display_name")
            or link.get("asset_label")
            or link.get("asset_id"),
            "Unknown promoter record",
        )
        species = _text(
            matched_reference.get("species") or source_snapshot.get("species"),
            "No species context recorded",
        )
        clade = _text(
            matched_reference.get("plant_clade") or source_snapshot.get("plant_clade"),
            "No plant clade recorded",
        )
        tissue_context = _text(
            source_snapshot.get("tissue_contexts"),
            "No tissue context recorded",
        )
        source_labels = _text(
            matched_reference.get("source_labels") or source_snapshot.get("source_labels"),
            "No source database recorded",
        )
        review_status = _text(
            matched_reference.get("review_status") or review_snapshot.get("curation_statuses"),
            "No curation status recorded",
        )
        manual_review_note = _text(
            review_snapshot.get("review_notes"),
            "No manual review note recorded",
        )
        explicit_missing_metadata_count = "missing_metadata_count" in review_snapshot
        if explicit_missing_metadata_count:
            missing_metadata_raw = review_snapshot.get("missing_metadata_count")
            missing_metadata_count = _text(missing_metadata_raw, "0")
            try:
                missing_metadata_value = int(str(missing_metadata_count).strip())
            except (TypeError, ValueError):
                missing_metadata_value = -1
        else:
            missing_metadata_count = ""
            missing_metadata_value = -1

        metadata_gap_parts: list[str] = []
        if source_labels == "No source database recorded":
            metadata_gap_parts.append("source metadata")
        if review_status == "No curation status recorded":
            metadata_gap_parts.append("review metadata")
        if species == "No species context recorded" or clade == "No plant clade recorded":
            metadata_gap_parts.append("species/clade context")
        if tissue_context == "No tissue context recorded":
            metadata_gap_parts.append("tissue context")

        if missing_metadata_value > 0:
            metadata_gap_text = (
                f"source/review metadata gap present ({missing_metadata_count} recorded metadata gap(s))"
            )
        elif missing_metadata_value == 0:
            metadata_gap_text = "source/review evidence metadata recorded"
        elif metadata_gap_parts:
            metadata_gap_text = (
                "source/review metadata gap present: missing "
                + ", ".join(metadata_gap_parts)
            )
        else:
            metadata_gap_text = "source/review metadata gap present; review source/review fields in documentation context"

        rows.append(
            {
                "Component Library promoter asset": promoter_label,
                "Species or clade context": f"{species}; {clade}",
                "Tissue evidence context": tissue_context,
                "Source/review metadata": (
                    f"source context: {source_labels}; "
                    f"review metadata: {review_status}"
                ),
                "Metadata gap": metadata_gap_text,
                "Manual review note": manual_review_note,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            _text(row.get("Component Library promoter asset")).casefold(),
            _text(row.get("Species or clade context")).casefold(),
            _text(row.get("Tissue evidence context")).casefold(),
        ),
    )


def _render_add_catalog_asset_reference_panel(
    project: dict[str, Any],
    project_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_id = project.get("id")
    records = load_seed_records()
    st.markdown(f"**{LINKED_CATALOG_ASSETS_ADD_PANEL_COPY}**")
    st.caption(
        "Search existing catalog assets only. This panel adds reference-only documentation links and does not edit "
        "catalog records."
    )
    st.caption("Each staged documentation reference keeps documentation-only context visible until it is linked to project documentation.")

    search_query = st.text_input(
        "Search existing catalog assets",
        key=f"pathway_catalog_asset_search_{project_id}",
        placeholder="Search by display name, alias, or tag",
    )
    matching_records = search_assets(records, search_query)
    if not matching_records:
        st.info("No catalog assets match the current search. Adjust the search text to continue.")
        return project_links

    selected_asset_id = st.selectbox(
        "Select catalog asset",
        options=[record.get("asset_id") for record in matching_records],
        format_func=lambda asset_id: asset_selector_label(_selected_asset_record(matching_records, asset_id)),
        key=f"pathway_catalog_asset_select_{project_id}",
    )
    selected_record = _selected_asset_record(matching_records, selected_asset_id)
    if selected_record:
        _render_selected_asset_preview(selected_record)

    selected_role = st.selectbox(
        "Select linkage role",
        options=list(ALLOWED_LINKAGE_ROLES),
        key=f"pathway_catalog_asset_role_{project_id}",
    )
    project_documentation_context = st.text_input(
        "Project documentation context",
        value=DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
        key=f"pathway_catalog_asset_context_{project_id}",
        help="Documentation-only context for where this reference belongs in the active project.",
    )
    documentation_note = st.text_area(
        "Optional documentation note",
        value=DEFAULT_DOCUMENTATION_NOTE,
        key=f"pathway_catalog_asset_note_{project_id}",
        height=90,
        placeholder="Optional local review note",
    )

    if st.button(
        "Add documentation reference",
        key=f"pathway_catalog_asset_add_{project_id}",
        use_container_width=True,
    ):
        try:
            link = build_project_asset_link(
                project_id=project_id,
                asset_id=selected_record.get("asset_id"),
                asset_display_name=selected_record.get("display_name"),
                asset_type=selected_record.get("asset_type"),
                linkage_role=selected_role,
                documentation_note=documentation_note or DEFAULT_DOCUMENTATION_NOTE,
                source_context_snapshot={
                    "catalog": "Local Design Asset Catalog",
                    "source_provenance_status": selected_record.get("provenance_status", ""),
                    "version_context": selected_record.get("version_context", ""),
                    "project_documentation_context": project_documentation_context or DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
                },
                review_status_snapshot={
                    "review_status": selected_record.get("review_status", ""),
                    "human_review_note": selected_record.get("human_review_notes", ""),
                },
                linked_at="session",
                human_review_required=True,
            )
            link["asset_snapshot"] = build_catalog_asset_snapshot(
                selected_record,
                asset_type=selected_record.get("asset_type"),
                fallback={
                    "asset_id": selected_record.get("asset_id"),
                    "asset_label": selected_record.get("display_name"),
                    "source_label": selected_record.get("provenance_status", ""),
                    "documentation_status": selected_record.get("review_status", ""),
                    "limitation_note": selected_record.get("documentation_boundary_note", DEFAULT_DOCUMENTATION_NOTE),
                },
            )
        except ValueError as exc:
            st.error(str(exc))
            return project_links

        basket_entry = basket_service.build_catalog_reference_basket_entry(
            project_id=project_id,
            link_payload=link,
            project_documentation_context=project_documentation_context or DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
            documentation_note=documentation_note or DEFAULT_DOCUMENTATION_NOTE,
        )
        if _find_persisted_project_link(
            project_id,
            asset_id=basket_entry.get("asset_id"),
            linkage_role=basket_entry.get("linkage_role"),
        ):
            st.info(LINKED_CATALOG_REFERENCE_EXISTS_COPY)
            return project_links

        basket_added, _existing_entry = basket_service.add_catalog_reference_basket_entry(
            st.session_state,
            basket_entry,
        )
        if not basket_added:
            st.info(basket_service.STAGED_REFERENCE_DUPLICATE_COPY)
            return project_links
        st.success(basket_service.STAGED_REFERENCE_ADDED_COPY)
        st.rerun()
        return project_links

    return project_links


def _link_basket_entry(project: dict[str, Any], basket_entry: dict[str, Any], project_links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    project_id = project.get("id")
    existing_link = _find_persisted_project_link(
        project_id,
        asset_id=basket_entry.get("asset_id"),
        linkage_role=basket_entry.get("linkage_role"),
    )
    if existing_link:
        basket_service.remove_catalog_reference_basket_entry(
            st.session_state,
            project_id=project_id,
            basket_id=basket_entry.get("basket_id"),
        )
        updated_links = _combined_project_links(project)
        st.session_state[_project_links_storage_key(project_id)] = updated_links
        st.info(LINKED_CATALOG_REFERENCE_EXISTS_AND_STAGED_REMOVED_COPY)
        return updated_links

    link = dict(basket_entry.get("link_payload") or {})
    source_snapshot = (
        link.get("source_context_snapshot")
        if isinstance(link.get("source_context_snapshot"), dict)
        else {}
    )
    source_snapshot["project_documentation_context"] = basket_entry.get(
        "project_documentation_context",
        DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
    )
    source_snapshot["reference_origin"] = basket_entry.get(
        "reference_origin",
        source_snapshot.get("reference_origin") or "Project documentation reference",
    )
    link["source_context_snapshot"] = source_snapshot
    link["documentation_note"] = basket_entry.get("documentation_note") or link.get("documentation_note")

    try:
        added, message, _stored_link = persistent_links.add_project_catalog_asset_link(link)
        updated_links = _combined_project_links(project)
    except Exception as exc:
        st.error(
            "Linked catalog reference could not be saved to project documentation. "
            f"The staged documentation reference remains in the basket: {exc}"
        )
        return project_links

    st.session_state[_project_links_storage_key(project_id)] = updated_links
    if added:
        basket_service.remove_catalog_reference_basket_entry(
            st.session_state,
            project_id=project_id,
            basket_id=basket_entry.get("basket_id"),
        )
        st.success(message or "Catalog asset documentation reference saved.")
        st.rerun()
        return updated_links
    basket_service.remove_catalog_reference_basket_entry(
        st.session_state,
        project_id=project_id,
        basket_id=basket_entry.get("basket_id"),
    )
    st.info(message or LINKED_CATALOG_REFERENCE_EXISTS_AND_STAGED_REMOVED_COPY)
    return updated_links


def _render_reference_basket_panel(
    project: dict[str, Any],
    project_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_id = project.get("id")
    basket_rows = basket_service.list_catalog_reference_basket(st.session_state, project_id=project_id)
    st.markdown("**Reference basket**")
    st.caption(
        "Staged documentation references stay in session until they are linked into project documentation or cleared."
    )
    st.caption("Each staged documentation reference keeps documentation-only context visible before persistence.")
    st.caption(basket_service.BASKET_BOUNDARY_COPY)
    if not basket_rows:
        st.info(basket_service.EMPTY_BASKET_COPY)
        return project_links

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "staged_reference_label": row.get("staged_reference_label"),
                    "asset_display_name": row.get("asset_display_name"),
                    "record_identifier": row.get("record_identifier"),
                    "catalog_name_source": row.get("catalog_name_source"),
                    "catalog_source_status": row.get("catalog_source_status"),
                    "reference_origin": row.get("reference_origin"),
                    "project_documentation_context": row.get("project_documentation_context"),
                    "documentation_note": row.get("documentation_note"),
                }
                for row in basket_rows
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    if len(basket_rows) > 1 and st.button(
        "Clear staged documentation references",
        key=f"pathway_catalog_reference_basket_clear_{project_id}",
        use_container_width=True,
    ):
        basket_service.clear_catalog_reference_basket(st.session_state, project_id=project_id)
        st.success(basket_service.STAGED_REFERENCE_CLEARED_COPY)
        st.rerun()
        return project_links

    selected_basket_id = st.selectbox(
        "Select staged documentation reference",
        options=[row.get("basket_id") for row in basket_rows],
        format_func=lambda basket_id: next(
            (
                f"{row.get('asset_display_name')} / {row.get('record_identifier')}"
                for row in basket_rows
                if str(row.get("basket_id")) == str(basket_id)
            ),
            str(basket_id),
        ),
        key=f"pathway_catalog_reference_basket_select_{project_id}",
    )
    selected_entry = next(
        (row for row in basket_rows if str(row.get("basket_id")) == str(selected_basket_id)),
        {},
    )
    basket_action_left, basket_action_right = st.columns(2, gap="small")
    with basket_action_left:
        if st.button(
            "Add reference to project documentation",
            key=f"pathway_catalog_reference_basket_link_{project_id}",
            use_container_width=True,
        ):
            return _link_basket_entry(project, selected_entry, project_links)
    with basket_action_right:
        if st.button(
            "Remove staged documentation reference",
            key=f"pathway_catalog_reference_basket_remove_{project_id}",
            use_container_width=True,
        ):
            removed = basket_service.remove_catalog_reference_basket_entry(
                st.session_state,
                project_id=project_id,
                basket_id=selected_entry.get("basket_id"),
            )
            if removed:
                st.success(basket_service.STAGED_REFERENCE_REMOVED_COPY)
                st.rerun()
            else:
                st.info(basket_service.STAGED_REFERENCE_NOT_FOUND_COPY)
    return project_links


def _render_add_plant_promoter_reference_panel(
    project: dict[str, Any],
    project_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_id = project.get("id")
    st.markdown("**Add Component Library promoter asset reference**")
    st.caption(CATALOG_REFERENCE_BOUNDARY_NOTE)
    st.caption(CATALOG_REFERENCE_LIMITATION_NOTE)
    st.caption("Each staged documentation reference keeps documentation-only context visible until it is linked to project documentation.")

    filter_cols = st.columns(3, gap="small")
    with filter_cols[0]:
        selected_clade = st.selectbox(
            "Promoter clade filter",
            options=["all", "monocot", "dicot", "other / not specified"],
            key=f"pathway_promoter_catalog_clade_{project_id}",
        )
    with filter_cols[1]:
        selected_species = st.text_input(
            "Promoter species filter",
            key=f"pathway_promoter_catalog_species_{project_id}",
            placeholder="Optional species text",
        )
    with filter_cols[2]:
        selected_tissue = st.text_input(
            "Promoter tissue context filter",
            key=f"pathway_promoter_catalog_tissue_{project_id}",
            placeholder="Optional tissue context",
        )

    options = build_catalog_reference_options(
        plant_clade="" if selected_clade == "all" else selected_clade,
        species=selected_species,
        tissue_context=selected_tissue,
    )
    if not options:
        st.info(EMPTY_CATALOG_REFERENCE_MESSAGE)
        return project_links

    selected_part_id = st.selectbox(
        "Select Component Library promoter asset reference",
        options=[row["part_id"] for row in options],
        format_func=lambda part_id: _selected_promoter_option(options, part_id).get("select_label", str(part_id)),
        key=f"pathway_promoter_catalog_select_{project_id}",
    )
    _render_selected_promoter_preview(selected_part_id)

    selected_role = st.selectbox(
        "Component Library promoter asset reference role",
        options=list(ALLOWED_LINKAGE_ROLES),
        index=list(ALLOWED_LINKAGE_ROLES).index("source_review_context"),
        key=f"pathway_promoter_catalog_role_{project_id}",
    )
    project_documentation_context = st.text_input(
        "Component Library promoter asset project documentation context",
        value=DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
        key=f"pathway_promoter_catalog_context_{project_id}",
        help="Documentation-only context for where this profile reference belongs in the active project.",
    )
    documentation_note = st.text_area(
        "Component Library promoter asset reference note",
        value=DEFAULT_PROMOTER_REFERENCE_NOTE,
        key=f"pathway_promoter_catalog_note_{project_id}",
        height=90,
        placeholder="Optional local review note",
    )

    if st.button(
        "Add Component Library promoter asset documentation reference",
        key=f"pathway_promoter_catalog_add_{project_id}",
        use_container_width=True,
    ):
        try:
            link = build_promoter_catalog_project_link(
                project_id=project_id,
                part_id=selected_part_id,
                linkage_role=selected_role,
                documentation_note=documentation_note or DEFAULT_PROMOTER_REFERENCE_NOTE,
                linked_at="session",
            )
        except ValueError as exc:
            st.error(str(exc))
            return project_links
        source_snapshot = (
            link.get("source_context_snapshot")
            if isinstance(link.get("source_context_snapshot"), dict)
            else {}
        )
        source_snapshot["project_documentation_context"] = (
            project_documentation_context or DEFAULT_PROJECT_DOCUMENTATION_CONTEXT
        )
        link["source_context_snapshot"] = source_snapshot
        basket_entry = basket_service.build_catalog_reference_basket_entry(
            project_id=project_id,
            link_payload=link,
            project_documentation_context=project_documentation_context or DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
            documentation_note=documentation_note or DEFAULT_PROMOTER_REFERENCE_NOTE,
        )
        if _find_persisted_project_link(
            project_id,
            asset_id=basket_entry.get("asset_id"),
            linkage_role=basket_entry.get("linkage_role"),
        ):
            st.info(LINKED_CATALOG_REFERENCE_EXISTS_COPY)
            return project_links
        basket_added, _existing_entry = basket_service.add_catalog_reference_basket_entry(
            st.session_state,
            basket_entry,
        )
        if not basket_added:
            st.info(basket_service.STAGED_REFERENCE_DUPLICATE_COPY)
            return project_links
        st.success(basket_service.STAGED_REFERENCE_ADDED_COPY)
        st.rerun()
        return project_links

    return project_links


def _link_option_label(link: dict[str, Any]) -> str:
    label = str(link.get("asset_display_name") or link.get("asset_label") or link.get("asset_id") or "").strip()
    asset_type = str(link.get("asset_type") or "").strip()
    role = str(link.get("linkage_role") or "").strip()
    suffix = " / ".join(value for value in (asset_type, role) if value)
    return f"{label} ({suffix})" if suffix else label


def _render_remove_catalog_asset_reference_panel(
    project: dict[str, Any],
    project_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not project_links:
        return project_links
    project_id = project.get("id")
    removable_links = [link for link in project_links if isinstance(link, dict)]
    if not removable_links:
        return project_links

    st.markdown("**Remove catalog asset reference**")
    st.caption(
        "Remove a project documentation reference only. This does not edit catalog records or promoter profiles."
    )
    selected_key = st.selectbox(
        "Select linked catalog reference to remove",
        options=[
            str(link.get("link_id") or f"{link.get('asset_id')}::{link.get('linkage_role')}")
            for link in removable_links
        ],
        format_func=lambda key: _link_option_label(
            next(
                (
                    link
                    for link in removable_links
                    if str(link.get("link_id") or f"{link.get('asset_id')}::{link.get('linkage_role')}") == str(key)
                ),
                {},
            )
        ),
        key=f"pathway_catalog_asset_remove_select_{project_id}",
    )
    selected_link = next(
        (
            link
            for link in removable_links
            if str(link.get("link_id") or f"{link.get('asset_id')}::{link.get('linkage_role')}") == str(selected_key)
        ),
        {},
    )
    if st.button(
        "Remove documentation reference",
        key=f"pathway_catalog_asset_remove_{project_id}",
        use_container_width=True,
    ):
        try:
            removed, message = persistent_links.remove_project_catalog_asset_link(
                project_id=project_id,
                link_id=selected_link.get("link_id"),
                asset_id=selected_link.get("asset_id"),
                linkage_role=selected_link.get("linkage_role"),
            )
        except Exception as exc:
            removed = False
            message = f"Database unavailable; reference was not removed: {exc}"
        if removed:
            updated_links = _combined_project_links(project)
            st.session_state[_project_links_storage_key(project_id)] = updated_links
            st.success(message)
            st.rerun()
            return updated_links
        st.info(message)
    return project_links


def render_linked_catalog_assets_section(project: dict[str, Any] | None) -> None:
    st.subheader("Linked Catalog Assets")
    st.caption(LINKED_CATALOG_ASSETS_BOUNDARY_COPY)
    st.caption(LINKED_CATALOG_ASSETS_SUMMARY_NOTE)
    if not project:
        st.info(LINKED_CATALOG_ASSETS_EMPTY_STATE_COPY)
        return

    project_links = list_project_asset_links(_combined_project_links(project), project_id=project.get("id"))
    with st.expander("Add catalog references", expanded=False):
        project_links = _render_add_catalog_asset_reference_panel(project, project_links)
        project_links = _render_add_plant_promoter_reference_panel(project, project_links)
        project_links = _render_reference_basket_panel(project, project_links)
    with st.expander("Remove catalog references", expanded=False):
        project_links = _render_remove_catalog_asset_reference_panel(project, project_links)
    rows = _asset_link_rows_from_links(project_links)
    summary = summarize_project_asset_links(project_links)
    review_rows = report_links_needing_review(project_links)
    promoter_summary = summarize_linked_plant_promoter_references(project_links)

    st.markdown("**Linked catalog assets summary**")
    st.caption("Documentation-only summary for linked catalog references, review context, and metadata-gap readback.")
    with st.container(border=True):
        with tool_typography.temporary_streamlit_binding(st):
            tool_typography.render_compact_summary_cards(
                [
                    ("Total linked assets", str(summary.get("total_links", 0)), "Documentation references"),
                    ("Asset types", str(len(summary.get("by_asset_type") or {})), "Grouped by recorded type"),
                    ("Linkage roles", str(len(summary.get("by_linkage_role") or {})), "Recorded project roles"),
                    ("Links needing human review", str(summary.get("human_review_required", 0)), "Manual review context"),
                ]
            )

    if summary.get("by_asset_type"):
        st.caption("count by asset type")
        st.caption(", ".join(f"{key}: {value}" for key, value in summary["by_asset_type"].items()))
    if summary.get("by_linkage_role"):
        st.caption("count by linkage role")
        st.caption(", ".join(f"{key}: {value}" for key, value in summary["by_linkage_role"].items()))
    st.caption("Source/status language: persistent records, bundled seed records, example catalog records, and documentation-only reference records may all appear in this workspace panel.")
    st.caption("Bridge fields shown below keep record identifier, catalog reference context, source/review context, evidence metadata, and project documentation note visible in one place.")
    st.caption("Where linked records already carry host/chassis-related source text or metadata, the table also shows a read-only recorded-context readback. That readback is source context only, not compatibility evidence.")
    st.caption("Linked catalog reference rows keep metadata gaps visible for human review; they do not endorse or select assets, verify sources, or judge downstream-use state.")
    if review_rows:
        st.caption("Links needing human review remain visible for documentation review.")
    else:
        st.caption("No linked catalog references are currently flagged for additional human review.")
    st.markdown("**Component Library Promoter Asset Readback**")
    st.caption(
        "Component Library promoter asset context is shown separately from the generic linked catalog asset table so project review can distinguish general documentation links from promoter-specific source context."
    )
    st.caption(
        "Compact Component Library promoter asset readback for project review: source context, tissue evidence context, "
        "review metadata, manual review note, and metadata gaps remain visible in one place."
    )
    st.caption(
        "Documentation-only context. This readback is not a promoter recommendation, not a host compatibility proof, "
        "not an expression prediction, not experimental validation, and not a wet-lab readiness judgment."
    )
    promoter_readback_rows = _promoter_context_readback_rows(project_links)
    if promoter_summary.get("linked_promoter_count"):
        st.caption(
            "Component Library promoter asset references: "
            f"{promoter_summary.get('linked_promoter_count', 0)} linked; "
            f"{promoter_summary.get('missing_metadata_count', 0)} missing metadata fields recorded."
        )
        st.caption(
            "Pinned documentation snapshots: "
            f"{promoter_summary.get('pinned_snapshot_count', 0)} pinned; "
            f"{promoter_summary.get('missing_snapshot_count', 0)} fallback metadata link(s)."
        )
        st.caption(str(promoter_summary.get("limitation_note") or CATALOG_REFERENCE_LIMITATION_NOTE))
        if promoter_readback_rows:
            st.dataframe(
                pd.DataFrame(promoter_readback_rows, columns=PROMOTER_CONTEXT_READBACK_COLUMNS),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Component Library promoter asset references are linked, but no promoter asset readback rows are available for documentation review yet.")
    elif rows:
        st.caption(PROMOTER_READBACK_EMPTY_WITH_GENERIC_LINKS_COPY)
    else:
        st.caption(PROMOTER_READBACK_EMPTY_NO_PROMOTER_COPY)

    if not rows:
        st.info(LINKED_CATALOG_ASSETS_EMPTY_STATE_COPY)
        return

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Linked reference": row["linked_reference_label"],
                    "Asset display name": row["asset_display_name"],
                    "Asset type": row["asset_type"],
                    "Record identifier": row["record_identifier"],
                    "Linkage role": row["linkage_role"],
                    "Reference origin": row["reference_origin"],
                    "Project documentation context": row["project_documentation_context"],
                    "Catalog source/status": row["catalog_source_status"],
                    "Source context readback": row["source_context_readback"],
                    "Host / chassis context readback": row["host_chassis_context_readback"],
                    "Review-needed context": row["review_needed_context"],
                    "Metadata gap context": row["metadata_gap_context"],
                    "Catalog reference context": row["catalog_reference_context"],
                    "Link state": row["linked_persisted_status"],
                    "Snapshot state": (
                        "pinned documentation snapshot"
                        if catalog_asset_snapshot_has_content(row["asset_snapshot"])
                        else "live metadata fallback"
                    ),
                    "Documentation note": row["documentation_note"],
                    "Asset snapshot": _snapshot_text(row["asset_snapshot"]),
                    "Source context snapshot": _snapshot_text(row["source_context_snapshot"]),
                    "Review status snapshot": _snapshot_text(row["review_status_snapshot"]),
                    "Human review required": row["human_review_required"],
                }
                for row in rows
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
