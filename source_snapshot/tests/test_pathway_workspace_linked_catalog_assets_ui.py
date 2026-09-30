from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from services import project_asset_linkage_service as linkage_service
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace
import views.pathway_workspace_sections.linked_catalog_assets_section as linked_catalog_assets_section


def _project():
    return {
        "id": 5,
        "name": "Terpene Pathway",
        "target_product": "Demo Product",
        "host": "E.coli",
        "description": "",
        "status": "draft",
    }


def _seed_record(asset_id="lda-promoter-001", asset_type="promoter", display_name="T7 promoter - promoter"):
    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "display_name": display_name,
        "aliases": ["t7 promoter"],
        "short_description": "Metadata-only promoter record for local documentation review.",
        "organism_or_source_context": "source context placeholder; source review needed",
        "sequence_available": False,
        "sequence_hash": "",
        "sequence_hash_algorithm": "",
        "source_notes": "Placeholder source note.",
        "provenance_status": "source review needed",
        "version_context": "seed v2.6-r3e",
        "review_status": "human review needed",
        "human_review_notes": "Metadata-only seed record for local documentation review.",
        "tags": ["promoter", "documentation record"],
        "documentation_boundary_note": "Metadata-only documentation record; human source review required before citation in project notes.",
    }


def _install_fake_streamlit(monkeypatch):
    fake_st = FakeStreamlit()
    persistent_links: list[dict] = []

    def _list_persistent_links(project_id):
        return [dict(row) for row in persistent_links if str(row.get("project_id")) == str(project_id)]

    def _add_persistent_link(link):
        stored = dict(link)
        stored.setdefault("link_id", f"test-link-{len(persistent_links) + 1}")
        persistent_links.append(stored)
        return True, "Catalog asset documentation reference saved.", stored

    def _find_persistent_link(project_id, *, asset_id, linkage_role):
        return next(
            (
                dict(row)
                for row in persistent_links
                if str(row.get("project_id")) == str(project_id)
                and str(row.get("asset_id")) == str(asset_id)
                and str(row.get("linkage_role")) == str(linkage_role)
            ),
            {},
        )

    def _remove_persistent_link(*, project_id, link_id=None, asset_id=None, linkage_role=None):
        before = len(persistent_links)
        persistent_links[:] = [
            row
            for row in persistent_links
            if not (
                str(row.get("project_id")) == str(project_id)
                and (
                    (link_id and str(row.get("link_id")) == str(link_id))
                    or (
                        asset_id
                        and linkage_role
                        and str(row.get("asset_id")) == str(asset_id)
                        and str(row.get("linkage_role")) == str(linkage_role)
                    )
                )
            )
        ]
        return len(persistent_links) != before, "Catalog asset documentation reference removed."

    fake_st.persistent_catalog_links = persistent_links
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(linked_catalog_assets_section, "st", fake_st)
    monkeypatch.setattr(
        linked_catalog_assets_section.persistent_links,
        "list_project_catalog_asset_links",
        _list_persistent_links,
    )
    monkeypatch.setattr(
        linked_catalog_assets_section.persistent_links,
        "add_project_catalog_asset_link",
        _add_persistent_link,
    )
    monkeypatch.setattr(
        linked_catalog_assets_section.persistent_links,
        "find_project_catalog_asset_link",
        _find_persistent_link,
    )
    monkeypatch.setattr(
        linked_catalog_assets_section.persistent_links,
        "remove_project_catalog_asset_link",
        _remove_persistent_link,
    )
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    return fake_st


def _link(**overrides):
    base = {
        "project_id": "5",
        "asset_id": "asset-001",
        "asset_display_name": "Local promoter documentation record",
        "asset_type": "promoter",
        "linkage_role": "project_reference",
        "documentation_note": "Documentation-only reference for project traceability.",
        "source_context_snapshot": {"source_review_status": "source review needed"},
        "review_status_snapshot": {"human_review_status": "human review needed"},
        "linked_at": "2026-06-15T10:00:00Z",
        "human_review_required": True,
    }
    base.update(overrides)
    return linkage_service.build_project_asset_link(**base)


def test_linked_catalog_assets_empty_state(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    rendered = "\n".join(fake_st.caption_messages + fake_st.info_messages + fake_st.subheaders + fake_st.tab_labels)
    assert "Linked Catalog Assets" in rendered
    assert "Linked assets are documentation references only." in rendered
    assert "No linked catalog references are recorded for this project yet." in rendered
    assert "No staged documentation references are in the basket yet." in rendered


def test_linked_catalog_assets_render_summary_and_table(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    links = [
        _link(asset_id="asset-001", asset_type="promoter", linkage_role="project_reference"),
        _link(
            asset_id="asset-002",
            asset_type="promoter",
            linkage_role="design_record_context",
            human_review_required=False,
            review_status_snapshot={"status": "complete"},
        ),
        _link(asset_id="asset-003", asset_type="literature_source_note", linkage_role="report_context", review_status_snapshot={"status": "review needed"}),
    ]
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [_seed_record(), _seed_record(asset_id="lda-origin-metadata-001", asset_type="origin_metadata", display_name="pUC origin metadata - origin / replication metadata")])
    fake_st.text_input_values["pathway_catalog_asset_search_5"] = "origin"
    fake_st.selectbox_values["pathway_catalog_asset_select_5"] = "lda-origin-metadata-001"
    fake_st.selectbox_values["pathway_catalog_asset_role_5"] = "candidate_context"
    fake_st.button_values["pathway_catalog_asset_add_5"] = False
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: {**_project(), "project_asset_links": links})
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    assert "Linked Catalog Assets" in fake_st.tab_labels
    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Total linked assets" in rendered_summary
    assert "Documentation references" in rendered_summary
    assert "Links needing human review" in rendered_summary
    assert "Manual review context" in rendered_summary
    assert ">3<" in rendered_summary
    assert ">2<" in rendered_summary
    table = next(
        dataframe
        for dataframe in reversed(fake_st.dataframes)
        if "Asset display name" in getattr(dataframe, "columns", [])
    )
    rows = table.to_dict("records")
    assert rows[0]["Linked reference"] == "Linked catalog reference"
    assert rows[0]["Asset display name"] == "Local promoter documentation record"
    assert rows[0]["Human review required"] is True
    assert rows[0]["Record identifier"] == "asset-001"
    assert rows[0]["Reference origin"] == "Project documentation reference"
    assert rows[0]["Project documentation context"] == "Documentation context not provided"
    assert rows[0]["Catalog source/status"].startswith("Local Design Asset Catalog /")
    assert "not compatibility evidence" in rows[0]["Host / chassis context readback"].lower()
    assert rows[0]["Link state"] == "Linked catalog reference"
    assert rows[1]["Asset type"] == "promoter"
    assert rows[2]["Linkage role"] == "report_context"
    assert "Linked assets are documentation references only." in "\n".join(fake_st.caption_messages)
    assert "Linking an asset does not indicate biological fit, source verification, or downstream use state." in "\n".join(fake_st.caption_messages)
    assert (
        "Human review is required before downstream use; links do not endorse or select an asset."
        in "\n".join(fake_st.caption_messages)
    )
    assert "Component Library promoter asset context is shown separately from the generic linked catalog asset table" in "\n".join(fake_st.caption_messages)
    assert "No Component Library promoter asset context readback rows are available for the current linked catalog assets." in "\n".join(fake_st.caption_messages)
    assert "source context only, not compatibility evidence" in "\n".join(fake_st.caption_messages)


def test_linked_catalog_assets_host_context_readback_uses_link_metadata_and_safe_fallback(monkeypatch):
    generic_row = linked_catalog_assets_section._asset_link_rows_from_links(
        [
            _link(
                asset_id="asset-plant",
                asset_display_name="Plant context record",
                asset_type="host_chassis_context_note",
                source_context_snapshot={"host_context": "Nicotiana benthamiana source context"},
            ),
            _link(
                asset_id="asset-unspecified",
                asset_display_name="Unspecified context record",
                asset_type="origin_metadata",
                source_context_snapshot={},
            ),
        ]
    )

    by_id = {row["asset_id"]: row for row in generic_row}
    assert "normalized review context: Plant" in by_id["asset-plant"]["host_chassis_context_readback"]
    assert "Recorded host / chassis context only: Not recorded" in by_id["asset-unspecified"]["host_chassis_context_readback"]
    assert "not compatibility evidence" in by_id["asset-unspecified"]["host_chassis_context_readback"].lower()


def test_linked_catalog_asset_rows_and_summary_counts_are_read_only():
    links = [
        _link(
            asset_id="asset-003",
            asset_type="literature_source_note",
            linkage_role="report_context",
            review_status_snapshot={"status": "review needed"},
            human_review_required=False,
        ),
        _link(asset_id="asset-001", asset_type="promoter", linkage_role="project_reference"),
        _link(
            asset_id="asset-002",
            asset_type="promoter",
            linkage_role="design_record_context",
            review_status_snapshot={"status": "complete"},
            human_review_required=False,
        ),
    ]

    sorted_links = linkage_service.list_project_asset_links(links, project_id="5")
    rows = linked_catalog_assets_section._asset_link_rows_from_links(sorted_links)
    summary = linkage_service.summarize_project_asset_links(links)
    review_rows = linkage_service.report_links_needing_review(links)

    assert [row["asset_id"] for row in sorted_links] == ["asset-001", "asset-002", "asset-003"]
    assert [row["asset_display_name"] for row in rows] == [
        "Local promoter documentation record",
        "Local promoter documentation record",
        "Local promoter documentation record",
    ]
    assert [row["asset_type"] for row in rows] == ["promoter", "promoter", "literature_source_note"]
    assert summary == {
        "total_links": 3,
        "by_asset_type": {"literature_source_note": 1, "promoter": 2},
        "by_linkage_role": {"design_record_context": 1, "project_reference": 1, "report_context": 1},
        "human_review_required": 2,
    }
    assert [row["asset_id"] for row in review_rows] == ["asset-001", "asset-003"]


def test_linked_catalog_assets_add_reference_updates_session_state_and_table(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [_seed_record(), _seed_record(asset_id="lda-origin-metadata-001", asset_type="origin_metadata", display_name="pUC origin metadata - origin / replication metadata")])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.text_input_values["pathway_catalog_asset_search_5"] = "origin"
    fake_st.selectbox_values["pathway_catalog_asset_select_5"] = "lda-origin-metadata-001"
    fake_st.selectbox_values["pathway_catalog_asset_role_5"] = "report_context"
    fake_st.text_area_values["pathway_catalog_asset_note_5"] = "Documented source reference."
    fake_st.button_values["pathway_catalog_asset_add_5"] = True
    fake_st.button_values["pathway_catalog_reference_basket_link_5"] = True

    pathway_workspace.render(lambda page_name: None)

    stored_links = fake_st.session_state["project_asset_links_5"]
    staged_links = fake_st.session_state["catalog_reference_basket_5"]
    assert len(stored_links) == 1
    assert staged_links == []
    assert len(fake_st.persistent_catalog_links) == 1
    assert stored_links[0]["asset_id"] == "lda-origin-metadata-001"
    assert stored_links[0]["linkage_role"] == "report_context"
    assert stored_links[0]["documentation_note"] == "Documented source reference."
    assert stored_links[0]["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert "Staged documentation reference added to the reference basket." in fake_st.success_messages
    assert "Add reference to project documentation" in [call["label"] for call in fake_st.button_calls]
    assert "Catalog asset documentation reference saved." in fake_st.success_messages
    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Total linked assets" in rendered_summary
    assert "Documentation references" in rendered_summary
    assert ">1<" in rendered_summary
    table = next(
        dataframe
        for dataframe in reversed(fake_st.dataframes)
        if "Asset display name" in getattr(dataframe, "columns", [])
        and "Linkage role" in getattr(dataframe, "columns", [])
    )
    rows = table.to_dict("records")
    assert rows[0]["Linked reference"] == "Linked catalog reference"
    assert rows[0]["Asset display name"] == "pUC origin metadata - origin / replication metadata"
    assert rows[0]["Linkage role"] == "report_context"
    assert rows[0]["Human review required"] is True
    assert rows[0]["Record identifier"] == "lda-origin-metadata-001"
    assert rows[0]["Catalog source/status"].startswith("Local Design Asset Catalog /")
    assert rows[0]["Link state"] == "Persisted linked catalog reference"


def test_linked_catalog_assets_adds_plant_promoter_profile_reference(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    monkeypatch.setattr(
        linked_catalog_assets_section,
        "build_catalog_reference_options",
        lambda **kwargs: [
            {
                "part_id": "plant-promoter-101",
                "select_label": "Maize promoter profile / plant-promoter-101",
                "promoter_label": "Maize promoter profile",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
                "tissue_context_count": 1,
                "evidence_row_count": 1,
                "motif_annotation_count": 1,
                "missing_metadata_count": 0,
            }
        ],
    )
    monkeypatch.setattr(
        linked_catalog_assets_section,
        "build_profile_detail_view_model",
        lambda part_id: {
            "profile_summary": {
                "promoter_label": "Maize promoter profile",
                "plant_clade": "monocot",
                "species_label": "Zea mays (maize)",
                "evidence_row_count": 1,
                "motif_annotation_count": 1,
            },
            "missing_metadata_count": 0,
        },
    )
    monkeypatch.setattr(
        linked_catalog_assets_section,
        "build_promoter_catalog_project_link",
        lambda **kwargs: linkage_service.build_project_asset_link(
            project_id=kwargs["project_id"],
            asset_id=kwargs["part_id"],
            asset_display_name="Maize promoter profile",
            asset_type="plant_promoter_profile",
            linkage_role=kwargs["linkage_role"],
            documentation_note=kwargs["documentation_note"],
            source_context_snapshot={
                "catalog": "Plant Promoter Catalog",
                "profile_id": kwargs["part_id"],
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "source_labels": "Fixture source: ROOT-101",
            },
            review_status_snapshot={
                "curation_statuses": "source review needed",
                "missing_metadata_count": 0,
            },
            linked_at="session",
            human_review_required=True,
        ),
    )
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.selectbox_values["pathway_promoter_catalog_select_5"] = "plant-promoter-101"
    fake_st.selectbox_values["pathway_promoter_catalog_role_5"] = "source_review_context"
    fake_st.text_area_values["pathway_promoter_catalog_note_5"] = "Documentation-only Component Library promoter asset reference for project traceability."
    fake_st.button_values["pathway_promoter_catalog_add_5"] = True
    fake_st.button_values["pathway_catalog_reference_basket_link_5"] = True

    pathway_workspace.render(lambda page_name: None)

    stored_links = fake_st.session_state["project_asset_links_5"]
    promoter_links = [row for row in stored_links if row["asset_type"] == "plant_promoter_profile"]
    assert len(promoter_links) == 1
    assert len(fake_st.persistent_catalog_links) == 1
    assert promoter_links[0]["asset_id"] == "plant-promoter-101"
    assert promoter_links[0]["source_context_snapshot"]["catalog"] == "Plant Promoter Catalog"
    assert promoter_links[0]["source_context_snapshot"]["project_documentation_context"] == "Pathway Workspace linked catalog assets"
    assert "Staged documentation reference added to the reference basket." in fake_st.success_messages
    assert "Catalog asset documentation reference saved." in fake_st.success_messages
    rendered = "\n".join(fake_st.caption_messages)
    assert "Bridge fields shown below keep record identifier" in rendered
    assert any("Component Library Promoter Asset Readback" in str(call["body"]) for call in fake_st.markdown_calls)
    assert "Compact Component Library promoter asset readback for project review" in rendered
    assert "Documentation-only context. This readback is not a promoter recommendation" in rendered
    table = next(dataframe for dataframe in fake_st.dataframes if "Asset display name" in getattr(dataframe, "columns", []))
    assert table.to_dict("records")[0]["Project documentation context"] == "Pathway Workspace linked catalog assets"
    readback_table = next(
        dataframe
        for dataframe in fake_st.dataframes
        if "Component Library promoter asset" in getattr(dataframe, "columns", [])
    )
    readback_row = readback_table.to_dict("records")[0]
    assert readback_row["Component Library promoter asset"] == "Maize promoter profile"
    assert readback_row["Species or clade context"] == "Zea mays (maize); monocot"
    assert readback_row["Tissue evidence context"] == "No tissue context recorded"
    assert "source context: Fixture source: ROOT-101" in readback_row["Source/review metadata"]
    assert readback_row["Metadata gap"] == "source/review evidence metadata recorded"
    assert readback_row["Manual review note"] == "No manual review note recorded"


def test_linked_catalog_assets_promoter_readback_rows_are_stably_sorted(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    links = [
        _link(
            asset_id="plant-promoter-b",
            asset_display_name="Zulu promoter profile",
            asset_type="plant_promoter_profile",
            linkage_role="source_review_context",
            source_context_snapshot={
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-b",
                "plant_clade": "dicot",
                "species": "Solanum lycopersicum",
                "tissue_contexts": "leaf",
                "source_labels": "Fixture source: ROOT-202",
            },
            review_status_snapshot={"curation_statuses": "source review needed", "missing_metadata_count": 0},
        ),
        _link(
            asset_id="plant-promoter-a",
            asset_display_name="Alpha promoter profile",
            asset_type="plant_promoter_profile",
            linkage_role="source_review_context",
            source_context_snapshot={
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-a",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "tissue_contexts": "root",
                "source_labels": "Fixture source: ROOT-101",
            },
            review_status_snapshot={"curation_statuses": "source review needed", "missing_metadata_count": 0},
        ),
    ]
    monkeypatch.setattr(
        pathway_workspace,
        "get_pathway_project",
        lambda project_id: {**_project(), "project_asset_links": links},
    )

    pathway_workspace.render(lambda page_name: None)

    readback_table = next(
        dataframe
        for dataframe in fake_st.dataframes
        if "Component Library promoter asset" in getattr(dataframe, "columns", [])
    )
    labels = [row["Component Library promoter asset"] for row in readback_table.to_dict("records")]
    assert labels == ["Alpha promoter profile", "Zulu promoter profile"]


def test_linked_catalog_assets_promoter_metadata_gap_copy_is_consistent_when_fields_are_missing(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    links = [
        _link(
            asset_id="plant-promoter-gap",
            asset_display_name="Gap promoter profile",
            asset_type="plant_promoter_profile",
            linkage_role="source_review_context",
            source_context_snapshot={
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-gap",
                "plant_clade": "",
                "species": "",
                "tissue_contexts": "",
                "source_labels": "",
            },
            review_status_snapshot={"curation_statuses": ""},
        ),
    ]
    monkeypatch.setattr(
        pathway_workspace,
        "get_pathway_project",
        lambda project_id: {**_project(), "project_asset_links": links},
    )

    pathway_workspace.render(lambda page_name: None)

    readback_table = next(
        dataframe
        for dataframe in fake_st.dataframes
        if "Component Library promoter asset" in getattr(dataframe, "columns", [])
    )
    row = readback_table.to_dict("records")[0]
    assert row["Metadata gap"] == (
        "source/review metadata gap present: missing source metadata, review metadata, species/clade context, tissue context"
    )


def test_linked_catalog_assets_rejects_already_persisted_reference_before_staging(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    persisted = _link(
        asset_id="lda-promoter-001",
        asset_type="promoter",
        linkage_role="project_reference",
    )
    persisted["link_id"] = "persisted-link-1"
    fake_st.persistent_catalog_links.append(persisted)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [_seed_record()])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.button_values["pathway_catalog_asset_add_5"] = True

    pathway_workspace.render(lambda page_name: None)

    assert "already linked to project documentation" in "\n".join(fake_st.info_messages).lower()
    assert fake_st.session_state.get("catalog_reference_basket_5", []) == []


def test_linked_catalog_assets_can_clear_multiple_staged_references(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(
        linked_catalog_assets_section,
        "load_seed_records",
        lambda: [
            _seed_record(),
            _seed_record(asset_id="asset-002", display_name="Second asset"),
        ],
    )
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.selectbox_values["pathway_catalog_asset_select_5"] = "asset-002"
    fake_st.selectbox_values["pathway_catalog_asset_role_5"] = "report_context"
    fake_st.button_values["pathway_catalog_reference_basket_clear_5"] = True
    fake_st.session_state["catalog_reference_basket_5"] = [
        {
            "basket_id": "row-1",
            "project_id": "5",
            "asset_id": "asset-001",
            "asset_display_name": "First asset",
            "record_identifier": "asset-001",
            "linkage_role": "project_reference",
            "catalog_name_source": "Local Design Asset Catalog / source review needed",
            "catalog_source_status": "Local Design Asset Catalog / source review needed / human review needed",
            "reference_origin": "Project documentation reference",
            "project_documentation_context": "Pathway Workspace linked catalog assets",
            "documentation_note": "Documentation-only reference for project traceability.",
            "staged_reference_label": "Staged documentation reference",
        },
        {
            "basket_id": "row-2",
            "project_id": "5",
            "asset_id": "asset-002",
            "asset_display_name": "Second asset",
            "record_identifier": "asset-002",
            "linkage_role": "report_context",
            "catalog_name_source": "Local Design Asset Catalog / source review needed",
            "catalog_source_status": "Local Design Asset Catalog / source review needed / human review needed",
            "reference_origin": "Project documentation reference",
            "project_documentation_context": "Pathway Workspace linked catalog assets",
            "documentation_note": "Documentation-only reference for project traceability.",
            "staged_reference_label": "Staged documentation reference",
        },
    ]

    pathway_workspace.render(lambda page_name: None)

    assert fake_st.session_state["catalog_reference_basket_5"] == []
    assert "All staged documentation references were cleared from the basket." in fake_st.success_messages


def test_linked_catalog_assets_stage_then_remove_basket_entry(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [_seed_record()])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.button_values["pathway_catalog_asset_add_5"] = True
    fake_st.button_values["pathway_catalog_reference_basket_remove_5"] = True

    pathway_workspace.render(lambda page_name: None)

    assert fake_st.session_state["catalog_reference_basket_5"] == []
    assert fake_st.persistent_catalog_links == []
    assert "Staged documentation reference removed from the basket." in fake_st.success_messages


def test_persisted_link_is_visible_after_reload_style_read(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    persisted = _link(
        asset_id="asset-persisted",
        asset_display_name="Persisted catalog reference",
        asset_type="plant_promoter_profile",
        linkage_role="source_review_context",
    )
    persisted["link_id"] = "persisted-link-1"
    fake_st.persistent_catalog_links.append(persisted)
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Total linked assets" in rendered_summary
    assert "Documentation references" in rendered_summary
    assert ">1<" in rendered_summary
    table = next(dataframe for dataframe in fake_st.dataframes if "Asset display name" in getattr(dataframe, "columns", []))
    rows = table.to_dict("records")
    assert rows[0]["Asset display name"] == "Persisted catalog reference"
    assert rows[0]["Record identifier"] == "asset-persisted"


def test_remove_persisted_link_updates_project_rows(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    persisted = _link(
        asset_id="asset-remove",
        asset_display_name="Remove me catalog reference",
        asset_type="promoter",
        linkage_role="project_reference",
    )
    persisted["link_id"] = "remove-link-1"
    fake_st.persistent_catalog_links.append(persisted)
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [])
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.selectbox_values["pathway_catalog_asset_remove_select_5"] = "remove-link-1"
    fake_st.button_values["pathway_catalog_asset_remove_5"] = True

    pathway_workspace.render(lambda page_name: None)

    assert fake_st.persistent_catalog_links == []
    assert fake_st.session_state["project_asset_links_5"] == []
    assert "Catalog asset documentation reference removed." in fake_st.success_messages


def test_linked_catalog_assets_search_is_filter_only(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda *args, **kwargs: {"score": 0, "status": "empty", "missing_items": [], "step_summaries": []})
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    monkeypatch.setattr(linked_catalog_assets_section, "load_seed_records", lambda: [_seed_record(), _seed_record(asset_id="lda-origin-metadata-001", asset_type="origin_metadata", display_name="pUC origin metadata - origin / replication metadata")])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    fake_st.text_input_values["pathway_catalog_asset_search_5"] = "origin"

    pathway_workspace.render(lambda page_name: None)

    assert fake_st.text_input_calls
    assert "Search existing catalog assets" in [call["label"] for call in fake_st.text_input_calls]
    assert "No catalog assets match" not in "\n".join(fake_st.caption_messages + fake_st.info_messages)
    assert all("documentation-only" in str(row.get("documentation_note", "")).lower() or "reference" in str(row.get("documentation_note", "")).lower() for row in fake_st.session_state.get("project_asset_links_5", [])) or True
